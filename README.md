# Partner Customer Import Service

Python backend service for importing partner customer CSV exports and managing customer records.

The service uses Flask with Flask-RESTful for HTTP resources and Django ORM in standalone mode for persistence. It includes JWT authentication, role-based authorization, structured JSON errors, JSON logging, Prometheus metrics, health/readiness checks, idempotent imports, row-level import failures, retry support, and manual customer CRUD.

## API Summary

Public endpoints:

- `GET /healthz`
- `GET /readyz`
- `GET /metrics`
- `POST /v1/auth/token`

Protected endpoints:

- `POST /v1/imports` multipart upload with field `file`
- `GET /v1/imports`
- `GET /v1/imports/{job_id}`
- `GET /v1/imports/{job_id}/errors` downloads row-level import errors as CSV
- `POST /v1/imports/{job_id}/retry`
- `GET /v1/customers`
- `POST /v1/customers`
- `GET /v1/customers/{customer_id}`
- `PATCH /v1/customers/{customer_id}`
- `DELETE /v1/customers/{customer_id}` soft-deactivates a customer

## Import Behavior

- CSV files are copied to durable local storage and parsed from disk, avoiding whole-file memory loads.
- The default upload limit is `20MB`, which keeps imports simple and synchronous for the expected file size.
- Rows are processed one at a time inside short database transactions.
- Invalid rows are recorded in `ImportRowError`; valid rows keep importing.
- Required CSV headers must use exact names: `partner`, `email`, `name`, `status`, `tier`, and `updated_at`.
- Optional exact headers are `source_row`, `external_id`, `tags`, and `note`; additional columns are allowed and ignored by the importer.
- The CSV must include a partner column; partner values are read from each row.
- Wrapped operational export rows like `Grace` followed by `Hopper,...` are repaired into one logical CSV row.
- Matching prefers `(partner, external_id)` and falls back to normalized email.
- A new partner identifier can link to an existing customer by email.
- Newer `updated_at` values win; older or duplicate rows are skipped.
- Exact file re-uploads return the existing job.
- `Idempotency-Key` returns the same job for the same file and `409 Conflict` if reused for different file content.
- If any rows fail, the service can email the configured ops recipients with a summary and `failed_rows.csv` attachment.

## Local Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
flask --app customer_import_service.service_app:app run --port 8000
```

For one-command local startup with automatic migrations:

```bash
AUTO_MIGRATE=1 flask --app customer_import_service.service_app:app run --port 8000
```

## One-Command Docker Setup

On macOS, this script installs Docker Desktop with Homebrew if Docker is missing, starts Docker Desktop, builds the application image, starts PostgreSQL, runs migrations, and exposes the API at `http://localhost:8000`.

```bash
./start.sh
```

On macOS, you can also double-click `Start.command` from Finder.

The app and PostgreSQL both run inside Docker containers. Docker Desktop itself still runs on the host.

Useful Docker commands:

```bash
docker compose logs -f app
docker compose exec db psql -U crm_user -d customer_imports
docker compose down
```

## Demo Users

If `SERVICE_USERS_JSON` is not set, these development users are available:

- `admin` / `adminpass`
- `operator` / `operatorpass`
- `reader` / `readerpass`

Issue a token:

```bash
curl -s http://localhost:8000/v1/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"username":"operator","password":"operatorpass"}'
```

Upload the sample CSV:

```bash
TOKEN="<access token>"
curl -s http://localhost:8000/v1/imports \
  -H "Authorization: Bearer $TOKEN" \
  -H "Idempotency-Key: sample-2026-04-exports" \
  -F "file=@samples/partner_customers.csv"
```

## Configuration

- `DATABASE_URL`: defaults to `sqlite:///data/customers.sqlite3`; supports SQLite and PostgreSQL URLs.
- `IMPORT_STORAGE_DIR`: defaults to `data/imports`.
- `MAX_CONTENT_LENGTH`: upload limit in bytes, default `20971520` (`20MB`).
- `JWT_SECRET`: signing secret for bearer tokens.
- `JWT_TTL_SECONDS`: token lifetime, default `3600`.
- `SERVICE_USERS_JSON`: JSON object of users with `password_hash` and `roles`.
- `AUTO_MIGRATE`: run migrations at Flask startup when set to `1`.
- `IMPORT_FAILURE_RECIPIENTS`: comma-separated email recipients for failed-row notifications.
- `IMPORT_DETAILS_BASE_URL`: optional base URL used in notification emails, for example `https://internal.example.com`.
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_USE_TLS`, `SMTP_TIMEOUT_SECONDS`: SMTP settings.

Example `SERVICE_USERS_JSON`:

```json
{
  "operator@example.com": {
    "password_hash": "scrypt:32768:8:1$...",
    "roles": ["operator"]
  }
}
```

Generate hashes with `werkzeug.security.generate_password_hash`.

## Failure Emails

When an import finishes with failed rows, the service sends an email if `IMPORT_FAILURE_RECIPIENTS` and `SMTP_HOST` are configured. The email includes summary counts and a `failed_rows_<job_id>.csv` attachment containing the source row, field, error code, message, identity key, and raw row values.

If email is not configured or SMTP delivery fails, the import still completes and the job stores `notification_error` so operations can see that notification did not go out.

## Tests

```bash
pytest
```
