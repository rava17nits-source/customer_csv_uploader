from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import csv
import hashlib
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Iterable

from werkzeug.datastructures import FileStorage

from customer_import_service.db.models import Customer, ImportJob
from customer_import_service.errors import APIError
from customer_import_service.observability import IMPORT_JOBS, IMPORT_ROWS
from customer_import_service.repository import import_repository
from customer_import_service.repository.import_repository import ImportRepositoryError

logger = logging.getLogger("customer_import_service")
HEADER_ALIASES = {
    "row": "source_row",
    "upd": "updated_at",
}
CANONICAL_HEADERS = ["p", "row", "cid", "email", "name", "status", "tier", "upd", "tags", "note"]
REQUIRED_FIELDS = {"email", "name", "status", "tier", "updated_at"}
OPTIONAL_FIELDS = {"source_row", "tags", "note"}
IMPORT_FIELDS = REQUIRED_FIELDS | OPTIONAL_FIELDS
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
VALID_STATUSES = {choice[0] for choice in Customer.Status.choices}
VALID_TIERS = {choice[0] for choice in Customer.Tier.choices}


@dataclass
class NormalizedRow:
    source_row: str
    email: str
    name: str
    status: str
    tier: str
    updated_at: date
    tags: list[str]
    note: str
    raw: dict
    physical_line: int | None


class RowValidationError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        field: str = "",
        source_row: str = "",
        raw_row: dict | None = None,
        physical_line: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field
        self.source_row = source_row
        self.raw_row = raw_row or {}
        self.physical_line = physical_line


@dataclass
class ImportResult:
    job: ImportJob
    duplicate: bool = False
    http_status: int = 201


def build_header_map(headers: list[str]) -> dict[str, int]:
    field_map: dict[str, int] = {}
    for index, header in enumerate(headers):
        canonical = HEADER_ALIASES.get(header, header)
        if canonical in IMPORT_FIELDS and canonical not in field_map:
            field_map[canonical] = index

    missing = sorted(REQUIRED_FIELDS - set(field_map.keys()))
    if missing:
        logger.warning("import csv missing required columns", extra={"missing": missing, "headers": headers})
        raise APIError(
            422,
            "missing_required_columns",
            "The CSV file is missing required columns.",
            {"missing": missing, "headers": headers},
        )
    return field_map


def parse_date(value: str) -> date:
    value = value.strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError("expected YYYYMMDD or YYYY-MM-DD")


def split_tags(value: str) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in re.split(r"[;|]", value) if part.strip()]


def raw_row_from(headers: list[str], row: list[str]) -> dict:
    raw = {}
    for index, header in enumerate(headers):
        raw[header] = row[index].strip() if index < len(row) else ""
    if len(row) > len(headers):
        raw["_extra_columns"] = row[len(headers) :]
    return raw


def normalized_row(
    headers: list[str],
    field_map: dict[str, int],
    row: list[str],
    physical_line: int | None,
) -> NormalizedRow:
    raw = raw_row_from(headers, row)

    if len(row) != len(headers):
        raise RowValidationError(
            "column_count_mismatch",
            f"Expected {len(headers)} columns but received {len(row)}.",
            raw_row=raw,
            physical_line=physical_line,
        )

    def value(field: str) -> str:
        index = field_map.get(field)
        if index is None:
            return ""
        return row[index].strip()

    source_row = value("source_row")
    email = value("email").lower()
    name = " ".join(value("name").split())
    status = value("status").lower()
    tier = value("tier").lower()
    updated_raw = value("updated_at")
    for field_name, field_value in {
        "email": email,
        "name": name,
        "status": status,
        "tier": tier,
        "updated_at": updated_raw,
    }.items():
        if not field_value:
            raise RowValidationError(
                "missing_required_field",
                f"{field_name} is required.",
                field=field_name,
                source_row=source_row,
                raw_row=raw,
                physical_line=physical_line,
            )

    if not EMAIL_RE.match(email):
        raise RowValidationError(
            "invalid_email",
            "email must be a valid email address.",
            field="email",
            source_row=source_row,
            raw_row=raw,
            physical_line=physical_line,
        )
    if status not in VALID_STATUSES:
        raise RowValidationError(
            "invalid_status",
            f"status must be one of: {', '.join(sorted(VALID_STATUSES))}.",
            field="status",
            source_row=source_row,
            raw_row=raw,
            physical_line=physical_line,
        )
    if tier not in VALID_TIERS:
        raise RowValidationError(
            "invalid_tier",
            f"tier must be one of: {', '.join(sorted(VALID_TIERS))}.",
            field="tier",
            source_row=source_row,
            raw_row=raw,
            physical_line=physical_line,
        )

    try:
        updated_at = parse_date(updated_raw)
    except ValueError as exc:
        raise RowValidationError(
            "invalid_updated_at",
            "updated_at must be formatted as YYYYMMDD or YYYY-MM-DD.",
            field="updated_at",
            source_row=source_row,
            raw_row=raw,
            physical_line=physical_line,
        ) from exc

    return NormalizedRow(
        source_row=source_row,
        email=email,
        name=name,
        status=status,
        tier=tier,
        updated_at=updated_at,
        tags=split_tags(value("tags")),
        note=value("note"),
        raw=raw,
        physical_line=physical_line,
    )


def _parse_single_csv_line(line: str) -> list[str]:
    return next(csv.reader([line], skipinitialspace=False))


def parse_tolerant_csv_records(csv_lines: Iterable[str]) -> tuple[list[str], list[tuple[int, list[str]]]]:
    raw_header_line = ""
    header_line_number = 0
    numbered_lines = iter(enumerate(csv_lines, start=1))
    for line_number, raw_line in numbered_lines:
        if raw_line.strip():
            raw_header_line = raw_line.rstrip("\r\n")
            header_line_number = line_number
            break
    if not raw_header_line:
        logger.warning("empty csv uploaded")
        raise APIError(422, "empty_csv", "The uploaded CSV file is empty.")

    headers = [header.strip() for header in _parse_single_csv_line(raw_header_line)]
    expected_column_count = len(headers)

    parsed_records: list[tuple[int, list[str]]] = []
    current_row_text = ""
    current_row_start_line: int | None = None
    for line_number, raw_line in numbered_lines:
        line_without_newline = raw_line.rstrip("\r\n")
        if not line_without_newline.strip() and not current_row_text:
            continue
        if current_row_start_line is None:
            current_row_start_line = line_number

        # Some partner exports wrap one customer row across multiple file lines.
        # Keep adding lines until the parsed row has at least the header column count.
        current_row_text = (
            f"{current_row_text} {line_without_newline.strip()}" if current_row_text else line_without_newline
        )
        try:
            parsed_row = _parse_single_csv_line(current_row_text)
        except csv.Error:
            continue
        if len(parsed_row) < expected_column_count:
            continue
        parsed_records.append((current_row_start_line or line_number, parsed_row))
        current_row_text = ""
        current_row_start_line = None

    # If the file ended while a row was being assembled, keep that final row.
    # Field validation later decides whether it has missing/extra columns.
    if current_row_text:
        try:
            parsed_row = _parse_single_csv_line(current_row_text)
        except csv.Error as exc:
            logger.warning("malformed csv row at end of file", extra={"line": current_row_start_line})
            raise APIError(
                422,
                "malformed_csv",
                "The CSV file ended while a row was still malformed.",
                {"line": current_row_start_line},
            ) from exc
        parsed_records.append((current_row_start_line or header_line_number, parsed_row))

    return headers, parsed_records


def save_upload_to_storage(file_storage: FileStorage, storage_dir: str) -> tuple[str, str]:
    Path(storage_dir).mkdir(parents=True, exist_ok=True)
    hasher = hashlib.sha256()
    suffix = Path(file_storage.filename or "customers.csv").suffix or ".csv"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=storage_dir) as tmp:
        while True:
            chunk = file_storage.stream.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
            tmp.write(chunk)
        tmp_path = tmp.name
    return tmp_path, hasher.hexdigest()


def move_upload_to_job_path(tmp_path: str, storage_dir: str, job_id: str) -> str:
    target = Path(storage_dir) / f"{job_id}.csv"
    shutil.move(tmp_path, target)
    return str(target)


class CustomerImporter:
    def __init__(self, storage_dir: str) -> None:
        self.storage_dir = storage_dir

    def import_upload(
        self,
        file_storage: FileStorage,
        submitted_by: str,
        idempotency_key: str | None = None,
    ) -> ImportResult:
        if not file_storage or not file_storage.filename:
            logger.warning("import upload missing file")
            raise APIError(400, "missing_file", "Upload a CSV file using multipart field 'file'.")
        if Path(file_storage.filename).suffix.lower() != ".csv":
            logger.warning("import upload rejected due to file type", extra={"filename": file_storage.filename})
            raise APIError(400, "invalid_file_type", "Only .csv files are accepted.")

        logger.info("import upload started", extra={"submitted_by": submitted_by, "filename": file_storage.filename})
        tmp_path, file_sha256 = save_upload_to_storage(file_storage, self.storage_dir)
        try:
            existing_by_key = None
            if idempotency_key:
                existing_by_key = import_repository.find_job_by_idempotency_key(idempotency_key)
            if existing_by_key:
                if existing_by_key.file_sha256 and existing_by_key.file_sha256 != file_sha256:
                    logger.warning("idempotency key conflict", extra={"submitted_by": submitted_by})
                    raise APIError(
                        409,
                        "idempotency_key_conflict",
                        "This idempotency key was already used for a different file.",
                    )
                return ImportResult(existing_by_key, duplicate=True, http_status=200)

            duplicate = import_repository.find_duplicate_job(file_sha256)
            if duplicate:
                logger.info("duplicate import upload detected", extra={"job_id": str(duplicate.id)})
                return ImportResult(duplicate, duplicate=True, http_status=200)

            job = import_repository.create_import_job(
                filename=Path(file_storage.filename).name,
                file_sha256=file_sha256,
                idempotency_key=idempotency_key or None,
                submitted_by=submitted_by,
            )
            storage_path = move_upload_to_job_path(tmp_path, self.storage_dir, str(job.id))
            tmp_path = ""
            import_repository.save_import_storage_path(job, storage_path)
            self.process_job(job)
            logger.info(
                "import upload finished",
                extra={"job_id": str(job.id), "status": job.status, "failed_rows": job.failed_rows},
            )
            return ImportResult(job, duplicate=False, http_status=422 if job.status == ImportJob.Status.FAILED else 201)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

    def retry_job(self, original: ImportJob, submitted_by: str) -> ImportResult:
        if not original.storage_path or not os.path.exists(original.storage_path):
            logger.warning("import retry file unavailable", extra={"job_id": str(original.id)})
            raise APIError(409, "import_file_unavailable", "The original import file is not available for retry.")

        logger.info("import retry started", extra={"original_job_id": str(original.id), "submitted_by": submitted_by})
        job = import_repository.create_import_job(
            filename=original.filename,
            file_sha256=original.file_sha256,
            storage_path=original.storage_path,
            submitted_by=submitted_by,
            retry_of=original,
        )
        self.process_job(job)
        return ImportResult(job, duplicate=False, http_status=422 if job.status == ImportJob.Status.FAILED else 201)

    def process_job(self, job: ImportJob) -> None:
        try:
            with open(job.storage_path, "r", encoding="utf-8-sig", errors="replace", newline="") as handle:
                headers, records = parse_tolerant_csv_records(handle)
                field_map = build_header_map(headers)
                for physical_line, row in records:
                    self._process_record(job, headers, field_map, row, physical_line)
            self._finalize_job(job)
            logger.info(
                "import job processed",
                extra={"job_id": str(job.id), "status": job.status, "total_rows": job.total_rows},
            )
        except APIError as exc:
            logger.exception("import job failed with api error", extra={"job_id": str(job.id), "code": exc.code})
            import_repository.mark_job_failed(job, exc.message)
            IMPORT_JOBS.labels(job.status).inc()
            return
        except Exception as exc:
            logger.exception("import job failed unexpectedly", extra={"job_id": str(job.id)})
            import_repository.mark_job_failed(job, str(exc))
            IMPORT_JOBS.labels(job.status).inc()
            raise

    def _process_record(
        self,
        job: ImportJob,
        headers: list[str],
        field_map: dict[str, int],
        row: list[str],
        physical_line: int,
    ) -> None:
        job.total_rows += 1
        try:
            normalized = normalized_row(headers, field_map, row, physical_line)
            outcome = self._upsert_customer(normalized, job.submitted_by)
            if outcome == "created":
                job.created_rows += 1
            elif outcome == "updated":
                job.updated_rows += 1
            elif outcome == "linked":
                job.linked_rows += 1
            else:
                job.skipped_rows += 1
            IMPORT_ROWS.labels(outcome).inc()
            logger.info(
                "import row processed",
                extra={
                    "job_id": str(job.id),
                    "source_row": normalized.source_row,
                    "email": normalized.email,
                    "outcome": outcome,
                },
            )
        except RowValidationError as exc:
            job.failed_rows += 1
            import_repository.create_row_error(job, exc)
            IMPORT_ROWS.labels("failed").inc()
            logger.warning(
                "import row validation failed",
                extra={"job_id": str(job.id), "source_row": exc.source_row, "field": exc.field, "code": exc.code},
            )
        finally:
            import_repository.save_job_counts(job)

    def _finalize_job(self, job: ImportJob) -> None:
        import_repository.finalize_job(job)
        IMPORT_JOBS.labels(job.status).inc()

    def _upsert_customer(self, row: NormalizedRow, actor: str) -> str:
        try:
            return import_repository.upsert_customer(row, actor)
        except ImportRepositoryError as exc:
            logger.warning(
                "customer upsert rejected",
                extra={"source_row": row.source_row, "email": row.email, "field": exc.field, "code": exc.code},
            )
            raise RowValidationError(
                exc.code,
                exc.message,
                field=exc.field,
                source_row=row.source_row,
                raw_row=row.raw,
                physical_line=row.physical_line,
            ) from exc
