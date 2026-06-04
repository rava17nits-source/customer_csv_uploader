import csv
import io
import time
import uuid
from pathlib import Path

from customer_import_service.config import Config
from customer_import_service.db.models import Customer, ImportJob, ImportRowError


SAMPLE_CSV = Path("samples/partner_customers.csv").read_bytes()


def post_import(client, headers, data=SAMPLE_CSV, extra_headers=None):
    all_headers = dict(headers)
    if extra_headers:
        all_headers.update(extra_headers)
    return client.post(
        "/v1/imports",
        data={"file": (io.BytesIO(data), "customers.csv")},
        content_type="multipart/form-data",
        headers=all_headers,
    )


def wait_for_import_job(client, headers, job_id, timeout_seconds=15):
    deadline = time.time() + timeout_seconds
    last_body = None
    while time.time() < deadline:
        response = client.get(f"/v1/imports/{job_id}", headers=headers)
        assert response.status_code == 200
        body = response.get_json()
        last_body = body["job"]
        if last_body["status"] not in {"queued", "processing"}:
            return body
        time.sleep(0.05)
    raise AssertionError(f"Import job {job_id} did not finish: {last_body}")


def test_auth_is_required_for_customer_list(client):
    response = client.get("/v1/customers")
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "missing_bearer_token"


def test_auth_errors_are_json_when_exception_propagation_is_disabled(app):
    original_testing = app.config["TESTING"]
    original_propagate = app.config.get("PROPAGATE_EXCEPTIONS")
    try:
        app.config.update(TESTING=False, PROPAGATE_EXCEPTIONS=False)
        response = app.test_client().get("/v1/customers")
    finally:
        app.config["TESTING"] = original_testing
        app.config["PROPAGATE_EXCEPTIONS"] = original_propagate

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "missing_bearer_token"


def test_reader_cannot_import(client, reader_token):
    response = post_import(client, {"Authorization": f"Bearer {reader_token}"})
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "insufficient_scope"


def test_import_rejects_non_csv_uploads(client, auth_headers):
    response = client.post(
        "/v1/imports",
        data={"file": (io.BytesIO(b"not a csv"), "customers.txt")},
        content_type="multipart/form-data",
        headers=auth_headers,
    )
    assert response.status_code == 400
    body = response.get_json()
    assert body["error"]["code"] == "invalid_file_type"
    assert body["error"]["message"] == "Only .csv files are accepted."


def test_sample_import_partially_succeeds_and_records_row_errors(client, auth_headers):
    response = post_import(client, auth_headers)
    assert response.status_code == 202

    body = response.get_json()
    assert body["duplicate"] is False
    assert body["job"]["status"] == "queued"
    assert body["job"]["counts"]["total"] == 0
    assert set(body["links"].keys()) == {"self", "errors"}

    job_id = body["job"]["id"]
    finished = wait_for_import_job(client, auth_headers, job_id)
    assert finished["job"]["status"] in {"completed", "partial_failed"}
    assert finished["job"]["counts"]["total"] == 19
    assert finished["job"]["counts"]["failed"] == 3

    assert ImportRowError.objects.count() == 3

    ada = Customer.objects.get(email="ada@x.io")
    assert ada.p == "p2"
    assert ada.cid == "C1001"
    assert ada.name == "Ada L"
    assert ada.status == "inactive"
    assert ada.tier == "std"
    assert ada.tags == "vip"
    evelyn = Customer.objects.get(email="eve@x.io")
    assert evelyn.name == "Evelyn Granville"
    assert evelyn.tier == "ent"


def test_import_errors_download_as_csv(client, auth_headers):
    response = post_import(client, auth_headers)
    assert response.status_code == 202
    job_id = response.get_json()["job"]["id"]

    wait_for_import_job(client, auth_headers, job_id)

    errors_response = client.get(f"/v1/imports/{job_id}/errors", headers=auth_headers)
    assert errors_response.status_code == 200
    assert errors_response.mimetype == "text/csv"
    assert errors_response.headers["Content-Disposition"].startswith('attachment; filename="failed_rows_')

    rows = list(csv.reader(io.StringIO(errors_response.get_data(as_text=True))))
    assert rows[0] == ["p", "row", "cid", "email", "name", "status", "tier", "upd", "tags", "note", "errors"]
    assert any(row[1] == "007" and row[-1].startswith("invalid_email") for row in rows[1:])
    assert any("missing_required_field" in row[-1] for row in rows[1:])
    assert any("invalid_tier" in row[-1] for row in rows[1:])


def test_import_retry_endpoint_is_not_exposed(client, auth_headers):
    job_id = str(uuid.uuid4())
    response = client.post(f"/v1/imports/{job_id}/retry", headers=auth_headers)
    assert response.status_code == 404


def test_exact_file_reupload_returns_existing_job_without_reprocessing(client, auth_headers):
    first = post_import(client, auth_headers)
    assert first.status_code == 202
    second = post_import(client, auth_headers)
    assert second.status_code == 200
    assert second.get_json()["duplicate"] is True
    wait_for_import_job(client, auth_headers, first.get_json()["job"]["id"])
    assert ImportJob.objects.count() == 1


def test_idempotency_key_conflict_returns_409(client, auth_headers):
    first = post_import(client, auth_headers, extra_headers={"Idempotency-Key": "same-key"})
    assert first.status_code == 202

    other_csv = (
        b"p,row,cid,email,name,status,tier,upd,tags,note\n"
        b"p1,1,C2000,a@x.io,A Test,active,std,20260420,,\n"
    )
    second = post_import(client, auth_headers, data=other_csv, extra_headers={"Idempotency-Key": "same-key"})
    assert second.status_code == 409
    assert second.get_json()["error"]["code"] == "idempotency_key_conflict"
    wait_for_import_job(client, auth_headers, first.get_json()["job"]["id"])


def test_whole_file_validation_failure_returns_failed_import_job(client, auth_headers):
    bad_csv = b"email,name\nnobody@example.com,Nobody\n"
    response = post_import(client, auth_headers, data=bad_csv)
    assert response.status_code == 202
    assert response.get_json()["job"]["status"] == "queued"

    body = wait_for_import_job(client, auth_headers, response.get_json()["job"]["id"])
    assert body["job"]["status"] == "failed"
    assert body["job"]["error_message"] == "The CSV file is missing required columns."
    assert body["job"]["counts"]["total"] == 0


def test_import_rejects_alias_headers(client, auth_headers):
    alias_csv = b"p,row,cid,email,name,status,tier,upd,tags,note\np1,1,C2000,a@x.io,A Test,active,std,20260420,,\n"
    response = post_import(client, auth_headers, data=alias_csv)
    assert response.status_code == 202
    body = wait_for_import_job(client, auth_headers, response.get_json()["job"]["id"])
    assert body["job"]["status"] == "completed"


def test_import_allows_additional_columns_with_exact_headers(client, auth_headers):
    csv_with_extra_column = (
        b"p,row,cid,email,name,status,tier,upd,tags,note,ignored_column\n"
        b"p1,1,C2000,a@x.io,A Test,active,std,20260420,,,extra value\n"
    )
    response = post_import(client, auth_headers, data=csv_with_extra_column)
    assert response.status_code == 202
    body = wait_for_import_job(client, auth_headers, response.get_json()["job"]["id"])
    assert body["job"]["status"] == "completed"
    assert body["job"]["counts"]["created"] == 1


def test_import_requires_partner_and_cid_columns(client, auth_headers):
    csv_without_partner_and_cid = b"row,email,name,status,tier,upd,tags,note\n1,a@x.io,A Test,active,std,20260420,,\n"
    response = post_import(client, auth_headers, data=csv_without_partner_and_cid)
    assert response.status_code == 202
    body = wait_for_import_job(client, auth_headers, response.get_json()["job"]["id"])
    assert body["job"]["status"] == "failed"
    assert body["job"]["error_message"] == "The CSV file is missing required columns."


def test_default_upload_limit_is_20mb():
    assert Config.MAX_CONTENT_LENGTH == 20 * 1024 * 1024


def test_manual_customer_create_and_patch_preserve_internal_note_and_tags(client, auth_headers):
    create_response = client.post(
        "/v1/customers",
        json={
            "p": "p1",
            "cid": "M1",
            "email": "manual@x.io",
            "name": "Manual Customer",
            "status": "active",
            "tier": "pro",
            "tags": "vip; manual",
            "internal_note": "vip escalation path",
        },
        headers=auth_headers,
    )
    assert create_response.status_code == 201
    customer = create_response.get_json()["customer"]
    assert customer["p"] == "p1"
    assert customer["cid"] == "M1"
    assert customer["tags"] == "vip; manual"

    patch_response = client.patch(
        f"/v1/customers/{customer['id']}",
        json={"tier": "ent", "tags": "vip; success"},
        headers=auth_headers,
    )
    assert patch_response.status_code == 200
    patched = patch_response.get_json()["customer"]
    assert patched["tier"] == "ent"
    assert patched["tags"] == "vip; success"
    assert patched["internal_note"] == "vip escalation path"


def test_customer_create_accepts_csv_row_style_payload(client, auth_headers):
    create_response = client.post(
        "/v1/customers",
        json={
            "p": "p1",
            "row": "1",
            "cid": "CSV-001",
            "email": "csvstyle@x.io",
            "name": "CSV Style Customer",
            "status": "active",
            "tier": "pro",
            "upd": "2026-06-03",
            "tags": "alpha; beta |gamma",
            "note": "created from a CSV-like JSON payload",
        },
        headers=auth_headers,
    )

    assert create_response.status_code == 201
    customer = create_response.get_json()["customer"]
    assert customer["p"] == "p1"
    assert customer["cid"] == "CSV-001"
    assert customer["tags"] == "alpha; beta |gamma"
    assert customer["source_updated_at"] == "2026-06-03"


def test_customer_rejects_internal_metadata_field(client, auth_headers):
    response = client.post(
        "/v1/customers",
        json={
            "p": "p1",
            "cid": "M1",
            "email": "manual@x.io",
            "name": "Manual Customer",
            "status": "active",
            "tier": "pro",
            "internal_metadata": {"owner": "ops"},
        },
        headers=auth_headers,
    )

    assert response.status_code == 400
    body = response.get_json()
    assert body["error"]["code"] == "unknown_fields"
    assert "internal_metadata" in body["error"]["details"]["fields"]


def test_invalid_customer_id_returns_bad_uuid(client, auth_headers):
    response = client.get("/v1/customers/123", headers=auth_headers)

    assert response.status_code == 400
    body = response.get_json()
    assert body["error"]["code"] == "bad_uuid"
    assert body["error"]["message"] == "Customer ID must be a valid UUID."


def test_valid_customer_id_returns_404_when_missing(client, auth_headers):
    response = client.get(f"/v1/customers/{uuid.uuid4()}", headers=auth_headers)

    assert response.status_code == 404
    body = response.get_json()
    assert body["error"]["code"] == "customer_not_found"
    assert body["error"]["message"] == "Customer was not found."


def test_invalid_import_job_id_returns_bad_uuid(client, auth_headers):
    response = client.get("/v1/imports/123", headers=auth_headers)

    assert response.status_code == 400
    body = response.get_json()
    assert body["error"]["code"] == "bad_uuid"
    assert body["error"]["message"] == "Import job ID must be a valid UUID."


def test_valid_import_job_id_returns_404_when_missing(client, auth_headers):
    response = client.get(f"/v1/imports/{uuid.uuid4()}", headers=auth_headers)

    assert response.status_code == 404
    body = response.get_json()
    assert body["error"]["code"] == "import_not_found"
    assert body["error"]["message"] == "Import job was not found."
