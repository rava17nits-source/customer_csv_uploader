# Customer Import Service

## Purpose
This repository implements a customer import API for partner CSV exports. It supports customer CRUD, import-job tracking, row-level validation errors, and background processing of uploads.

## How It Runs
- The HTTP API is a Flask app in `customer_import_service/service_app.py`.
- Persistence uses the Django ORM models in `customer_import_service/db/`.
- Import uploads create an `ImportJob` row, store the CSV on disk, and start a dedicated child process for processing.
- The job runner lives in `customer_import_service/job_runner.py`.
- There is no retry endpoint; imports are handled once per upload and job state/counters are the source of truth.
- Local development can run with `flask --app customer_import_service.service_app:app run --port 8000`.
- Docker users should install Docker Desktop or Docker Engine first, then run `./start.sh`.
- The Docker setup starts the API and Postgres containers.

## Repo Structure
- `customer_import_service/` — application code
  - `resources.py` — HTTP resources and request validation
  - `controller/` — import parsing and job orchestration
  - `repository/` — database access helpers
  - `db/` — Django models, migrations, and ORM settings
  - `job_runner.py` — child-process entrypoint for a single import job
- `tests/` — API and behavior tests
- `samples/` — sample CSV input files
- `postman/` — Postman collection examples
- `README.md` — end-user setup and API documentation

## Dos
- Do keep API behavior and error codes stable unless a change is intentional.
- Do update tests when changing request validation, job state, or response payloads.
- Do keep logs useful and concise.
- Do keep secrets, passwords, tokens, and private keys out of the repo and out of logs.
- Do redact or omit email addresses, access tokens, session tokens, and other sensitive values from debug output unless they are required for a test.
- Do prefer small, focused changes that match the existing code style.
- Do update `README.md` when setup steps or runtime behavior change.

## Don’ts
- Don’t log secrets, authorization headers, JWTs, or raw credentials.
- Don’t commit `.env` files, API tokens, private keys, or database passwords.
- Don’t weaken authentication or authorization checks to make tests pass.
- Don’t add new dependencies unless the change genuinely needs them.
- Don’t change import-job status semantics without updating the API, tests, and docs together.
- Don’t store large binary artifacts or generated build outputs in the repo.
- Don’t use the request thread for long-running import work.

## Notes For Future Work
- The import flow is intentionally asynchronous so uploads return quickly.
- Job status and counts are the source of truth for import progress.
- Prefer the repository layer for database changes instead of writing ORM calls directly in resources.
