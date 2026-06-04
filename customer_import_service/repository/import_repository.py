from __future__ import annotations

from dataclasses import dataclass
import logging
import uuid

from django.db import IntegrityError, transaction
from django.utils import timezone

from customer_import_service.db.models import Customer, ImportJob, ImportRowError
from customer_import_service.errors import APIError


logger = logging.getLogger("customer_import_service")


@dataclass
class ImportRepositoryError(Exception):
    code: str
    message: str
    field: str = ""


def find_job_by_idempotency_key(idempotency_key: str) -> ImportJob | None:
    return ImportJob.objects.filter(idempotency_key=idempotency_key).first()


def find_duplicate_job(file_sha256: str) -> ImportJob | None:
    return (
        ImportJob.objects.filter(file_sha256=file_sha256)
        .exclude(status=ImportJob.Status.FAILED)
        .order_by("-created_at")
        .first()
    )


def create_import_job(
    filename: str,
    file_sha256: str,
    submitted_by: str,
    idempotency_key: str | None = None,
    storage_path: str = "",
) -> ImportJob:
    logger.info("creating import job", extra={"uploaded_filename": filename, "submitted_by": submitted_by})
    return ImportJob.objects.create(
        status=ImportJob.Status.QUEUED,
        filename=filename,
        file_sha256=file_sha256,
        storage_path=storage_path,
        idempotency_key=idempotency_key or None,
        submitted_by=submitted_by,
        started_at=None,
    )


def save_import_storage_path(job: ImportJob, storage_path: str) -> None:
    logger.info("saving import storage path", extra={"job_id": str(job.id)})
    job.storage_path = storage_path
    job.save(update_fields=["storage_path", "updated_at"])


def mark_job_processing(job: ImportJob) -> None:
    job.status = ImportJob.Status.PROCESSING
    if job.started_at is None:
        job.started_at = timezone.now()
    job.save(update_fields=["status", "started_at", "updated_at"])


def mark_job_failed(job: ImportJob, message: str) -> None:
    logger.error("marking import job failed", extra={"job_id": str(job.id), "error_message": message})
    job.status = ImportJob.Status.FAILED
    job.error_message = message
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "error_message", "finished_at", "updated_at"])


def save_job_counts(job: ImportJob) -> None:
    job.save(
        update_fields=[
            "total_rows",
            "created_rows",
            "updated_rows",
            "linked_rows",
            "skipped_rows",
            "failed_rows",
            "updated_at",
        ]
    )


def create_row_error(job: ImportJob, error: object) -> None:
    logger.warning(
        "saving import row error",
        extra={"job_id": str(job.id), "source_row": error.source_row, "field": error.field, "code": error.code},
    )
    ImportRowError.objects.create(
        job=job,
        source_row=error.source_row,
        physical_line=error.physical_line,
        code=error.code,
        field=error.field,
        message=error.message,
        raw_row=error.raw_row,
    )


def finalize_job(job: ImportJob) -> None:
    successful_rows = job.created_rows + job.updated_rows + job.linked_rows + job.skipped_rows
    if job.failed_rows and not successful_rows:
        job.status = ImportJob.Status.FAILED
        job.error_message = "No valid customer rows were imported."
    elif job.failed_rows:
        job.status = ImportJob.Status.PARTIAL_FAILED
    else:
        job.status = ImportJob.Status.COMPLETED
    logger.info("finalizing import job", extra={"job_id": str(job.id), "status": job.status})
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "error_message", "finished_at", "updated_at"])


def list_import_jobs(status: str | None = None) -> object:
    qs = ImportJob.objects.all().order_by("-created_at")
    if status:
        qs = qs.filter(status=status.strip().lower())
    return qs


def _import_job_uuid(job_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(job_id))
    except (TypeError, ValueError) as exc:
        raise APIError(400, "bad_uuid", "Import job ID must be a valid UUID.") from exc


def get_import_job(job_id: str) -> ImportJob:
    job_uuid = _import_job_uuid(job_id)
    try:
        return ImportJob.objects.get(pk=job_uuid)
    except ImportJob.DoesNotExist as exc:
        raise APIError(404, "import_not_found", "Import job was not found.") from exc


def list_import_errors(job: ImportJob) -> object:
    return job.row_errors.order_by("id")


def iter_import_errors(job: ImportJob):
    return job.row_errors.order_by("id").iterator(chunk_size=500)


def upsert_customer(row: object, actor: str) -> str:
    with transaction.atomic():
        customer = Customer.objects.select_for_update().filter(p=row.p, cid=row.cid).first()
        if customer is None:
            customer = Customer.objects.select_for_update().filter(email=row.email).first()

        if customer is None:
            logger.info("creating customer from import", extra={"email": row.email, "actor": actor})
            customer = Customer.objects.create(
                p=row.p,
                cid=row.cid,
                email=row.email,
                name=row.name,
                status=row.status,
                tier=row.tier,
                tags=row.tags,
                note=row.note,
                source_updated_at=row.updated_at,
                last_imported_at=timezone.now(),
                created_by=actor,
                updated_by=actor,
            )
            return "created"

        if customer.source_updated_at and row.updated_at <= customer.source_updated_at:
            logger.info("skipping stale customer import row", extra={"email": row.email, "actor": actor})
            return "skipped_stale"

        if Customer.objects.exclude(pk=customer.pk).filter(p=row.p, cid=row.cid).exists():
            logger.warning("partner/cid conflict during import", extra={"p": row.p, "cid": row.cid, "actor": actor})
            raise ImportRepositoryError(
                "identifier_conflict",
                "partner and cid are already attached to another customer.",
                field="cid",
            )

        if Customer.objects.exclude(pk=customer.pk).filter(email=row.email).exists():
            logger.warning("email conflict during import", extra={"email": row.email, "actor": actor})
            raise ImportRepositoryError(
                "email_conflict",
                "email is already attached to another customer.",
                field="email",
            )

        customer.email = row.email
        customer.p = row.p
        customer.cid = row.cid
        customer.name = row.name
        customer.status = row.status
        customer.tier = row.tier
        customer.tags = row.tags
        customer.note = row.note
        customer.source_updated_at = row.updated_at
        customer.last_imported_at = timezone.now()
        customer.updated_by = actor
        customer.save(
            update_fields=[
                "email",
                "p",
                "cid",
                "name",
                "status",
                "tier",
                "tags",
                "note",
                "source_updated_at",
                "last_imported_at",
                "updated_by",
                "updated_at",
            ]
        )
        logger.info("updated customer from import", extra={"email": row.email, "actor": actor})
        return "updated"
