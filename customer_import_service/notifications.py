from __future__ import annotations

import csv
import io

from customer_import_service.db.models import ImportJob
from customer_import_service.repository import import_repository


def failed_rows_csv(job: ImportJob) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    row_errors = list(import_repository.iter_import_errors(job))
    if not row_errors:
        writer.writerow(["errors"])
        return output.getvalue()

    raw_headers: list[str] = []
    for row_error in row_errors:
        raw_row = row_error.raw_row or {}
        raw_headers = [
            header
            for header in raw_row.keys()
            if header != "_extra_columns"
        ]
        if raw_headers:
            break

    writer.writerow([*raw_headers, "errors"])
    for row_error in row_errors:
        raw_row = row_error.raw_row or {}
        row_values = [raw_row.get(header, "") for header in raw_headers]
        error_parts = [row_error.message]
        if row_error.code:
            error_parts.insert(0, row_error.code)
        if row_error.field:
            error_parts.append(f"field={row_error.field}")
        if row_error.physical_line:
            error_parts.append(f"line={row_error.physical_line}")
        writer.writerow(
            [
                *row_values,
                " | ".join(error_parts),
            ]
        )
    return output.getvalue()
