from pathlib import Path
import json
import os

from werkzeug.security import generate_password_hash


BASE_DIR = Path(__file__).resolve().parent.parent


def bool_from_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def int_from_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    return int(raw)


def list_from_env(name: str) -> list[str]:
    raw = os.getenv(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def import_storage_dir() -> str:
    return os.getenv("IMPORT_STORAGE_DIR", str(BASE_DIR / "data" / "imports"))


def service_users() -> dict:
    raw = os.getenv("SERVICE_USERS_JSON")
    if raw:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise RuntimeError("SERVICE_USERS_JSON must be a JSON object keyed by username")
        return data

    return {
        "admin": {
            "password_hash": generate_password_hash("adminpass"),
            "roles": ["admin"],
        },
        "operator": {
            "password_hash": generate_password_hash("operatorpass"),
            "roles": ["operator"],
        },
        "reader": {
            "password_hash": generate_password_hash("readerpass"),
            "roles": ["reader"],
        },
    }


class Config:
    JSON_SORT_KEYS = False
    MAX_CONTENT_LENGTH = int_from_env("MAX_CONTENT_LENGTH", 20 * 1024 * 1024)
    JWT_SECRET = os.getenv("JWT_SECRET", "development-jwt-secret-change-me")
    JWT_ISSUER = os.getenv("JWT_ISSUER", "customer-import-service")
    JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "customer-import-api")
    JWT_TTL_SECONDS = int_from_env("JWT_TTL_SECONDS", 3600)
    AUTH_DISABLED = bool_from_env("AUTH_DISABLED", False)
    AUTO_MIGRATE = bool_from_env("AUTO_MIGRATE", False)
    IMPORT_STORAGE_DIR = import_storage_dir()
    SERVICE_USERS = service_users()
    IMPORT_DETAILS_BASE_URL = os.getenv("IMPORT_DETAILS_BASE_URL", "")
    LOG_DIR = os.getenv("LOG_DIR", str(BASE_DIR / "logs"))
