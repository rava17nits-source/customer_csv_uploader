from pathlib import Path
import os


def configure_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "customer_import_service.db.settings")
    import django
    from django.apps import apps

    if not apps.ready:
        django.setup()


def ensure_parent_dirs() -> None:
    configure_django()
    from django.conf import settings

    default_db = settings.DATABASES["default"]
    if default_db["ENGINE"] == "django.db.backends.sqlite3" and default_db["NAME"] != ":memory:":
        Path(default_db["NAME"]).parent.mkdir(parents=True, exist_ok=True)


def migrate_database(verbosity: int = 0) -> None:
    ensure_parent_dirs()
    from django.core.management import call_command

    call_command("migrate", interactive=False, verbosity=verbosity)
