from pathlib import Path
import os
from urllib.parse import unquote, urlparse


BASE_DIR = Path(__file__).resolve().parents[2]

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "development-django-secret")
INSTALLED_APPS = ["customer_import_service.db.apps.CustomerImportServiceConfig"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = os.getenv("TIME_ZONE", "UTC")
MIDDLEWARE = []
ROOT_URLCONF = "customer_import_service.db.empty_urls"


def _database_from_url() -> dict:
    url = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'data' / 'customers.sqlite3'}")
    parsed = urlparse(url)

    if parsed.scheme == "sqlite":
        if parsed.path in ("", "/:memory:"):
            name = ":memory:"
        else:
            name = unquote(parsed.path)
            Path(name).parent.mkdir(parents=True, exist_ok=True)
        return {"ENGINE": "django.db.backends.sqlite3", "NAME": name}

    if parsed.scheme in {"postgres", "postgresql"}:
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": parsed.path.lstrip("/"),
            "USER": unquote(parsed.username or ""),
            "PASSWORD": unquote(parsed.password or ""),
            "HOST": parsed.hostname or "",
            "PORT": str(parsed.port or ""),
        }

    raise RuntimeError(f"Unsupported DATABASE_URL scheme: {parsed.scheme}")


DATABASES = {"default": _database_from_url()}
