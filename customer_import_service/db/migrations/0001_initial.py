import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Customer",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
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
                ("tags", models.JSONField(blank=True, default=list)),
                ("note", models.TextField(blank=True)),
                ("internal_note", models.TextField(blank=True)),
                ("internal_metadata", models.JSONField(blank=True, default=dict)),
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
                            ("processing", "Processing"),
                            ("completed", "Completed"),
                            ("partial_failed", "Partial Failed"),
                            ("failed", "Failed"),
                        ],
                        default="processing",
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
                (
                    "retry_of",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="customer_import_service.importjob",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="CustomerIdentifier",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("partner", models.CharField(max_length=64)),
                ("external_id", models.CharField(max_length=128)),
                ("first_seen_at", models.DateTimeField(auto_now_add=True)),
                ("last_seen_at", models.DateTimeField(auto_now=True)),
                (
                    "customer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="identifiers",
                        to="customer_import_service.customer",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="ImportRowError",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
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
            model_name="customeridentifier",
            constraint=models.UniqueConstraint(fields=("partner", "external_id"), name="uniq_partner_external_id"),
        ),
        migrations.AddIndex(
            model_name="customeridentifier",
            index=models.Index(fields=["partner", "external_id"], name="idx_ident_partner_external"),
        ),
        migrations.AddIndex(
            model_name="customeridentifier",
            index=models.Index(fields=["customer"], name="idx_identifier_customer"),
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
