# Partner Customer Import Service

Python backend service for importing partner customer CSV exports and managing customer records.

The service uses Flask with Flask-RESTful for HTTP resources and Django ORM in standalone mode for persistence. It includes JWT authentication, role-based authorization, structured JSON errors, JSON logging, Prometheus metrics, health/readiness checks, idempotent imports, row-level import failures, and manual customer CRUD.

## API Summary

Public endpoints:
- `POST /v1/auth/token`

Protected endpoints:

- `POST /v1/imports` multipart upload with field `file` returns `202 Accepted` and starts a child process
- `GET /v1/imports` lists all uploaded jobs for the current user
- `GET /v1/imports?status=queued` lists waiting jobs
- `GET /v1/imports?status=processing` lists active jobs
- `GET /v1/imports/{job_id}` gets one job by job id
- `GET /v1/imports/{job_id}/errors` downloads row-level import errors as CSV
- `GET /v1/customers`
- `POST /v1/customers`
- `GET /v1/customers/{customer_id}`
- `PATCH /v1/customers/{customer_id}`
- `DELETE /v1/customers/{customer_id}` soft-deactivates a customer

## Import Behavior

- CSV files are copied to durable local storage and parsed from disk, avoiding whole-file memory loads.
- The default upload limit is `20MB`, which keeps uploads predictable for the expected file size.
- Rows are processed one at a time inside short database transactions.
- Invalid rows are recorded in `ImportRowError`; valid rows keep importing.
- Uploads are accepted quickly, stored durably, and processed asynchronously by a dedicated child process spawned per upload.
- `queued` jobs have been accepted but have not yet started; `processing` jobs are actively running in their child process.
- Required CSV headers must use exact names: `p`, `cid`, `email`, `name`, `status`, `tier`, and `upd` or `updated_at`.
- Optional exact headers are `row`, `tags`, and `note`; additional columns are allowed and ignored by the importer.
- The CSV must include `p` and `cid` values on each row.
- Wrapped operational export rows like `Grace` followed by `Hopper,...` are repaired into one logical CSV row.
- Matching prefers `(p, cid)` and falls back to normalized email.
- A new `(p, cid)` pair can link to an existing customer by email.
- Newer `updated_at` values win; older or duplicate rows are skipped.
- Exact file re-uploads return the existing job.
- `Idempotency-Key` returns the same job for the same file and `409 Conflict` if reused for different file content.
- If any rows fail, the job is marked `partial_failed` or `failed`, and you can download the row-level errors as CSV.

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

Install Docker Desktop or Docker Engine for your OS first. Once Docker is set up, simply run `./start.sh`. The script assumes `docker` and `docker compose` are already available.

- Docker Desktop download: https://www.docker.com/products/docker-desktop/
- Docker Engine install docs: https://docs.docker.com/engine/install/

On Linux, install Docker Engine plus the Docker Compose plugin. On macOS, Docker Desktop is the simplest option.

This setup is tested on macOS with Docker Desktop.

```bash
./start.sh
```

The app and PostgreSQL both run inside Docker containers. Docker Desktop itself still runs on the host.

Useful Docker commands:

```bash
docker compose logs -f app
docker compose exec db psql -U crm_user -d customer_imports
docker compose down
```

## Demo Users

FOR BETTER EXPERIENCE PLEASE IMPORT POSTMAN COLLECTIONS PUSHED IN THE REPO INTO POSTMAN APP.
IT WILL HAVE EVERYTHING IN ONE PLACE.

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

If you are running locally without Docker, the upload returns immediately and the child process handles the queued job.

## Configuration

- `DATABASE_URL`: defaults to `sqlite:///data/customers.sqlite3`; supports SQLite and PostgreSQL URLs.
- `IMPORT_STORAGE_DIR`: defaults to `data/imports`.
- `MAX_CONTENT_LENGTH`: upload limit in bytes, default `20971520` (`20MB`).
- `JWT_SECRET`: signing secret for bearer tokens.
- `JWT_TTL_SECONDS`: token lifetime, default `3600`.
- `SERVICE_USERS_JSON`: JSON object of users with `password_hash` and `roles`.
- `AUTO_MIGRATE`: run migrations at Flask startup when set to `1`.

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

## Tests

```bash
pytest
```
