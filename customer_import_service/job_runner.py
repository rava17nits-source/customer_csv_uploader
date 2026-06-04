from __future__ import annotations

import logging
import sys

from django.db import close_old_connections

from customer_import_service.config import Config
from customer_import_service.db import configure_django
from customer_import_service.errors import APIError


logger = logging.getLogger("customer_import_service")


def configure_process_logging() -> None:
    if logging.getLogger().handlers:
        return
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


def run_import_job(job_id: str) -> int:
    configure_process_logging()
    configure_django()
    from customer_import_service.controller.importer import CustomerImporter
    from customer_import_service.repository import import_repository

    close_old_connections()
    job = None
    try:
        job = import_repository.get_import_job(job_id)
        import_repository.mark_job_processing(job)
        CustomerImporter(Config.IMPORT_STORAGE_DIR).process_job(job)
        return 0
    except APIError as exc:
        logger.exception("import job process could not start", extra={"job_id": job_id, "code": exc.code})
        if job is not None:
            try:
                import_repository.mark_job_failed(job, exc.message)
            except Exception:
                logger.exception("failed to mark import job as failed", extra={"job_id": job_id})
        return 1
    except Exception as exc:
        logger.exception("unexpected import job process failure", extra={"job_id": job_id})
        if job is not None:
            try:
                import_repository.mark_job_failed(job, str(exc))
            except Exception:
                logger.exception("failed to mark import job as failed", extra={"job_id": job_id})
        return 1
    finally:
        close_old_connections()


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("Usage: python -m customer_import_service.job_runner <job_id>", file=sys.stderr)
        return 2
    return run_import_job(args[0])


if __name__ == "__main__":
    raise SystemExit(main())
