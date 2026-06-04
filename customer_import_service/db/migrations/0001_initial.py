import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Customer",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("p", models.CharField(blank=True, max_length=64, null=True)),
                ("cid", models.CharField(blank=True, max_length=128, null=True)),
                ("email", models.EmailField(max_length=254, unique=True)),
                ("name", models.CharField(max_length=255)),
                (
                    "status",
                    models.CharField(choices=[("active", "Active"), ("inactive", "Inactive")], max_length=16),
                ),
                (
                    "tier",
                    models.CharField(
                        choices=[("std", "Standard"), ("pro", "Pro"), ("ent", "Enterprise")],
                        max_length=16,
                    ),
                ),
                ("tags", models.TextField(blank=True, default="")),
                ("note", models.TextField(blank=True)),
                ("internal_note", models.TextField(blank=True)),
                ("source_updated_at", models.DateField(blank=True, null=True)),
                ("last_imported_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.CharField(blank=True, max_length=255)),
                ("updated_by", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="ImportJob",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("queued", "Queued"),
                            ("processing", "Processing"),
                            ("completed", "Completed"),
                            ("partial_failed", "Partial Failed"),
                            ("failed", "Failed"),
                        ],
                        default="queued",
                        max_length=32,
                    ),
                ),
                ("filename", models.CharField(blank=True, max_length=255)),
                ("file_sha256", models.CharField(blank=True, max_length=64)),
                ("storage_path", models.TextField(blank=True)),
                ("idempotency_key", models.CharField(blank=True, max_length=255, null=True)),
                ("submitted_by", models.CharField(blank=True, max_length=255)),
                ("total_rows", models.PositiveIntegerField(default=0)),
                ("created_rows", models.PositiveIntegerField(default=0)),
                ("updated_rows", models.PositiveIntegerField(default=0)),
                ("linked_rows", models.PositiveIntegerField(default=0)),
                ("skipped_rows", models.PositiveIntegerField(default=0)),
                ("failed_rows", models.PositiveIntegerField(default=0)),
                ("error_message", models.TextField(blank=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="ImportRowError",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_row", models.CharField(blank=True, max_length=64)),
                ("physical_line", models.PositiveIntegerField(blank=True, null=True)),
                ("identity_key", models.CharField(blank=True, max_length=255)),
                ("code", models.CharField(max_length=64)),
                ("field", models.CharField(blank=True, max_length=64)),
                ("message", models.TextField()),
                ("raw_row", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="row_errors",
                        to="customer_import_service.importjob",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="customer",
            constraint=models.UniqueConstraint(fields=("p", "cid"), name="uniq_customer_partner_cid"),
        ),
        migrations.AddIndex(
            model_name="customer",
            index=models.Index(fields=["p", "cid"], name="idx_customer_partner_cid"),
        ),
        migrations.AddIndex(
            model_name="customer",
            index=models.Index(fields=["email"], name="idx_customer_email"),
        ),
        migrations.AddIndex(
            model_name="customer",
            index=models.Index(fields=["status", "tier"], name="idx_customer_status_tier"),
        ),
        migrations.AddIndex(
            model_name="customer",
            index=models.Index(fields=["source_updated_at"], name="idx_customer_source_updated"),
        ),
        migrations.AddConstraint(
            model_name="importjob",
            constraint=models.UniqueConstraint(
                condition=models.Q(("idempotency_key__isnull", False)),
                fields=("idempotency_key",),
                name="uniq_import_idempotency_key",
            ),
        ),
        migrations.AddIndex(
            model_name="importjob",
            index=models.Index(fields=["file_sha256"], name="idx_import_file_sha"),
        ),
        migrations.AddIndex(
            model_name="importjob",
            index=models.Index(fields=["status", "created_at"], name="idx_import_status_created"),
        ),
        migrations.AddIndex(
            model_name="importrowerror",
            index=models.Index(fields=["job", "source_row"], name="idx_row_error_job_source_row"),
        ),
        migrations.AddIndex(
            model_name="importrowerror",
            index=models.Index(fields=["code"], name="idx_row_error_code"),
        ),
    ]
