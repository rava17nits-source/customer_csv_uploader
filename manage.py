#!/usr/bin/env python3
"""Django management entrypoint for the standalone ORM used by the Flask API."""

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "customer_import_service.db.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
