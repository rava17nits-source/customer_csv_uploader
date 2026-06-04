from __future__ import annotations

from datetime import date
from pathlib import Path

from flask import Response, current_app, request, url_for
from flask_ext.restful import Resource
import logging

from customer_import_service.auth import authenticate_credentials, issue_token, require_scopes
from customer_import_service.controller.importer import CustomerImporter, EMAIL_RE, VALID_STATUSES, VALID_TIERS, parse_date
from customer_import_service.db.models import ImportJob
from customer_import_service.errors import APIError
from customer_import_service.notifications import failed_rows_csv
from customer_import_service.repository import customer_repository, import_repository
from customer_import_service.serializers import (
    customer_to_dict,
    import_job_to_dict,
    paginate_queryset,
)


logger = logging.getLogger("customer_import_service")


def json_body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError(400, "invalid_json", "Request body must be a JSON object.")
    return data


def actor() -> str:
    claims = getattr(request, "auth", None)
    if claims:
        return claims.get("sub", "unknown")
    from flask import g

    return getattr(g, "auth", {}).get("sub", "unknown")


def links_for_job(job: ImportJob) -> dict:
    return {
        "self": url_for("importjobresource", job_id=str(job.id), _external=False),
        "errors": url_for("importerrorsresource", job_id=str(job.id), _external=False),
    }


def validate_customer_payload(data: dict, partial: bool = False) -> dict:
    allowed = {
        "p",
        "row",
        "cid",
        "email",
        "name",
        "status",
        "tier",
        "upd",
        "tags",
        "note",
        "internal_note",
        "source_updated_at",
    }
    unknown = sorted(set(data) - allowed)
    if unknown:
        logger.warning("customer payload contains unknown fields", extra={"fields": unknown})
        raise APIError(400, "unknown_fields", "Request body contains unknown fields.", {"fields": unknown})

    required = {"email", "name", "status", "tier"}
    missing = sorted(field for field in required if not partial and not data.get(field))
    if missing:
        logger.warning("customer payload missing required fields", extra={"fields": missing})
        raise APIError(422, "missing_required_fields", "Customer payload is missing required fields.", {"fields": missing})

    cleaned = {}
    if "email" in data:
        email = str(data["email"]).strip().lower()
        if not EMAIL_RE.match(email):
            logger.warning("invalid customer email provided")
            raise APIError(422, "invalid_email", "email must be a valid email address.")
        cleaned["email"] = email
    if "name" in data:
        name = " ".join(str(data["name"]).split())
        if not name:
            logger.warning("invalid customer name provided")
            raise APIError(422, "invalid_name", "name must not be empty.")
        cleaned["name"] = name
    if "status" in data:
        status = str(data["status"]).strip().lower()
        if status not in VALID_STATUSES:
            logger.warning("invalid customer status provided", extra={"status": status})
            raise APIError(422, "invalid_status", "status is not supported.", {"allowed": sorted(VALID_STATUSES)})
        cleaned["status"] = status
    if "tier" in data:
        tier = str(data["tier"]).strip().lower()
        if tier not in VALID_TIERS:
            logger.warning("invalid customer tier provided", extra={"tier": tier})
            raise APIError(422, "invalid_tier", "tier is not supported.", {"allowed": sorted(VALID_TIERS)})
        cleaned["tier"] = tier
    if "tags" in data:
        tags = data["tags"]
        if not isinstance(tags, str):
            raise APIError(422, "invalid_tags", "tags must be a string.")
        cleaned["tags"] = tags.strip()
    if "p" in data:
        cleaned["p"] = str(data["p"]).strip()
    if "cid" in data:
        cleaned["cid"] = str(data["cid"]).strip()
    if "note" in data:
        cleaned["note"] = str(data["note"])
    if "internal_note" in data:
        cleaned["internal_note"] = str(data["internal_note"])
    if "source_updated_at" in data and data["source_updated_at"]:
        try:
            cleaned["source_updated_at"] = parse_date(str(data["source_updated_at"]))
        except ValueError as exc:
            raise APIError(422, "invalid_source_updated_at", "source_updated_at must be YYYYMMDD or YYYY-MM-DD.") from exc
    if "upd" in data and data["upd"] and "source_updated_at" not in cleaned:
        try:
            cleaned["source_updated_at"] = parse_date(str(data["upd"]))
        except ValueError as exc:
            raise APIError(422, "invalid_upd", "upd must be YYYYMMDD or YYYY-MM-DD.") from exc
    return cleaned


class AuthTokenResource(Resource):
    def post(self):
        data = json_body()
        logger.info("auth token requested")
        username = str(data.get("username", ""))
        password = str(data.get("password", ""))
        auth = authenticate_credentials(username, password)
        token = issue_token(username, auth["roles"])
        return {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": current_app.config["JWT_TTL_SECONDS"],
            "roles": auth["roles"],
            "scopes": auth["scopes"],
        }, 200


class CustomerListResource(Resource):
    @require_scopes("customers:read")
    def get(self):
        logger.info("customer list requested", extra={"actor": actor()})
        qs = customer_repository.list_customers(request.args)
        page = max(int(request.args.get("page", 1)), 1)
        per_page = min(max(int(request.args.get("per_page", 50)), 1), 250)
        items, page_info = paginate_queryset(qs, page, per_page)
        return {
            "customers": [customer_to_dict(customer) for customer in items],
            "pagination": page_info,
        }, 200

    @require_scopes("customers:write")
    def post(self):
        cleaned = validate_customer_payload(json_body())
        cleaned.setdefault("source_updated_at", date.today())
        logger.info("customer create requested", extra={"actor": actor(), "email": cleaned.get("email", "")})
        customer = customer_repository.create_customer(cleaned, actor())
        return {"customer": customer_to_dict(customer)}, 201, {"Location": url_for("customerresource", customer_id=str(customer.id))}


class CustomerResource(Resource):
    @require_scopes("customers:read")
    def get(self, customer_id: str):
        logger.info("customer fetch requested", extra={"actor": actor(), "customer_id": customer_id})
        customer = self._customer(customer_id)
        return {"customer": customer_to_dict(customer)}, 200

    @require_scopes("customers:write")
    def patch(self, customer_id: str):
        customer = self._customer(customer_id)
        cleaned = validate_customer_payload(json_body(), partial=True)
        logger.info("customer update requested", extra={"actor": actor(), "customer_id": customer_id})
        customer = customer_repository.update_customer(customer, cleaned, actor())
        return {"customer": customer_to_dict(customer)}, 200

    @require_scopes("customers:write")
    def delete(self, customer_id: str):
        customer = self._customer(customer_id)
        logger.info("customer delete requested", extra={"actor": actor(), "customer_id": customer_id})
        customer_repository.deactivate_customer(customer, actor())
        return "", 204

    @staticmethod
    def _customer(customer_id: str):
        return customer_repository.get_customer(customer_id)


class ImportCollectionResource(Resource):
    @require_scopes("imports:write")
    def post(self):
        file_storage = request.files.get("file")
        idempotency_key = request.headers.get("Idempotency-Key")
        logger.info(
            "import upload requested",
            extra={"actor": actor(), "uploaded_filename": getattr(file_storage, "filename", "")},
        )
        importer = CustomerImporter(current_app.config["IMPORT_STORAGE_DIR"])
        result = importer.import_upload(
            file_storage=file_storage,
            submitted_by=actor(),
            idempotency_key=idempotency_key,
        )
        payload = {
            "job": import_job_to_dict(result.job),
            "duplicate": result.duplicate,
            "links": links_for_job(result.job),
        }
        headers = {"Location": url_for("importjobresource", job_id=str(result.job.id), _external=False)}
        return payload, result.http_status, headers

    @require_scopes("imports:read")
    def get(self):
        logger.info("import jobs requested", extra={"actor": actor()})
        qs = import_repository.list_import_jobs(request.args.get("status"))
        page = max(int(request.args.get("page", 1)), 1)
        per_page = min(max(int(request.args.get("per_page", 25)), 1), 100)
        jobs, page_info = paginate_queryset(qs, page, per_page)
        return {"imports": [import_job_to_dict(job) for job in jobs], "pagination": page_info}, 200


class ImportJobResource(Resource):
    @require_scopes("imports:read")
    def get(self, job_id: str):
        logger.info("import job requested", extra={"actor": actor(), "job_id": job_id})
        job = self._job(job_id)
        return {"job": import_job_to_dict(job), "links": links_for_job(job)}, 200

    @staticmethod
    def _job(job_id: str) -> ImportJob:
        return import_repository.get_import_job(job_id)


class ImportErrorsResource(Resource):
    @require_scopes("imports:read")
    def get(self, job_id: str):
        logger.info("failed rows download requested", extra={"actor": actor(), "job_id": job_id})
        job = ImportJobResource._job(job_id)
        response = Response(failed_rows_csv(job), mimetype="text/csv")
        response.headers["Content-Disposition"] = f'attachment; filename="failed_rows_{job.id}.csv"'
        return response


class HealthResource(Resource):
    def get(self):
        return {"status": "ok"}, 200


class ReadyResource(Resource):
    def get(self):
        try:
            customer_repository.count_customers()
        except Exception as exc:
            raise APIError(503, "database_unavailable", "Database is not ready.") from exc
        storage = Path(current_app.config["IMPORT_STORAGE_DIR"])
        return {"status": "ready", "storage": str(storage)}, 200
