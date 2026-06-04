from django.core.paginator import Paginator


def iso(value):
    if value is None:
        return None
    return value.isoformat()


def customer_to_dict(customer) -> dict:
    data = {
        "id": str(customer.id),
        "email": customer.email,
        "name": customer.name,
        "status": customer.status,
        "tier": customer.tier,
        "tags": customer.tags,
        "note": customer.note,
        "internal_note": customer.internal_note,
        "internal_metadata": customer.internal_metadata,
        "source_updated_at": iso(customer.source_updated_at),
        "last_imported_at": iso(customer.last_imported_at),
        "created_by": customer.created_by,
        "updated_by": customer.updated_by,
        "created_at": iso(customer.created_at),
        "updated_at": iso(customer.updated_at),
    }
    return data


def import_job_to_dict(job) -> dict:
    return {
        "id": str(job.id),
        "status": job.status,
        "filename": job.filename,
        "file_sha256": job.file_sha256,
        "idempotency_key": job.idempotency_key,
        "submitted_by": job.submitted_by,
        "retry_of": str(job.retry_of_id) if job.retry_of_id else None,
        "counts": {
            "total": job.total_rows,
            "created": job.created_rows,
            "updated": job.updated_rows,
            "linked": job.linked_rows,
            "skipped": job.skipped_rows,
            "failed": job.failed_rows,
        },
        "error_message": job.error_message,
        "started_at": iso(job.started_at),
        "finished_at": iso(job.finished_at),
        "created_at": iso(job.created_at),
        "updated_at": iso(job.updated_at),
    }


def row_error_to_dict(row_error) -> dict:
    return {
        "id": row_error.id,
        "source_row": row_error.source_row,
        "physical_line": row_error.physical_line,
        "identity_key": row_error.identity_key,
        "code": row_error.code,
        "field": row_error.field,
        "message": row_error.message,
        "raw_row": row_error.raw_row,
        "created_at": iso(row_error.created_at),
    }


def paginate_queryset(queryset, page: int, per_page: int) -> tuple[list, dict]:
    paginator = Paginator(queryset, per_page)
    current = paginator.get_page(page)
    return list(current.object_list), {
        "page": current.number,
        "per_page": per_page,
        "total_pages": paginator.num_pages,
        "total_items": paginator.count,
        "has_next": current.has_next(),
        "has_previous": current.has_previous(),
    }
