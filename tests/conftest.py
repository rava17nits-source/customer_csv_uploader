import os
import shutil
import tempfile

import pytest


TEST_ROOT = tempfile.mkdtemp(prefix="customer-import-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT}/test.sqlite3"
os.environ["IMPORT_STORAGE_DIR"] = f"{TEST_ROOT}/imports"
os.environ["JWT_SECRET"] = "test-jwt-secret-with-at-least-thirty-two-bytes"
os.environ["DJANGO_SECRET_KEY"] = "test-django-secret"
os.environ["AUTO_MIGRATE"] = "0"

from customer_import_service.db import migrate_database  # noqa: E402

migrate_database()

from customer_import_service.service_app import create_app  # noqa: E402
from customer_import_service.db.models import Customer, ImportJob, ImportRowError  # noqa: E402


@pytest.fixture(scope="session")
def app():
    return create_app({"TESTING": True, "AUTO_MIGRATE": False})


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def clean_database():
    ImportRowError.objects.all().delete()
    ImportJob.objects.all().delete()
    Customer.objects.all().delete()
    yield


@pytest.fixture()
def operator_token(client):
    response = client.post("/v1/auth/token", json={"username": "operator", "password": "operatorpass"})
    assert response.status_code == 200
    return response.get_json()["access_token"]


@pytest.fixture()
def reader_token(client):
    response = client.post("/v1/auth/token", json={"username": "reader", "password": "readerpass"})
    assert response.status_code == 200
    return response.get_json()["access_token"]


@pytest.fixture()
def auth_headers(operator_token):
    return {"Authorization": f"Bearer {operator_token}"}


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(TEST_ROOT, ignore_errors=True)
