import uuid

from django.db import models


class Customer(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    class Tier(models.TextChoices):
        STANDARD = "std", "Standard"
        PRO = "pro", "Pro"
        ENTERPRISE = "ent", "Enterprise"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=16, choices=Status.choices)
    tier = models.CharField(max_length=16, choices=Tier.choices)
    tags = models.JSONField(default=list, blank=True)
    note = models.TextField(blank=True)
    internal_note = models.TextField(blank=True)
    internal_metadata = models.JSONField(default=dict, blank=True)
    source_updated_at = models.DateField(null=True, blank=True)
    last_imported_at = models.DateTimeField(null=True, blank=True)
    created_by = models.CharField(max_length=255, blank=True)
    updated_by = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


    class Meta:
        indexes = [
            models.Index(fields=["email"], name="idx_customer_email"),
            models.Index(fields=["status", "tier"], name="idx_customer_status_tier"),
            models.Index(fields=["source_updated_at"], name="idx_customer_source_updated"),
        ]


class ImportJob(models.Model):
    class Status(models.TextChoices):
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        PARTIAL_FAILED = "partial_failed", "Partial Failed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PROCESSING)
    filename = models.CharField(max_length=255, blank=True)
    file_sha256 = models.CharField(max_length=64, blank=True)
    storage_path = models.TextField(blank=True)
    idempotency_key = models.CharField(max_length=255, null=True, blank=True)
    submitted_by = models.CharField(max_length=255, blank=True)
    retry_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL)
    total_rows = models.PositiveIntegerField(default=0)
    created_rows = models.PositiveIntegerField(default=0)
    updated_rows = models.PositiveIntegerField(default=0)
    linked_rows = models.PositiveIntegerField(default=0)
    skipped_rows = models.PositiveIntegerField(default=0)
    failed_rows = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=models.Q(idempotency_key__isnull=False),
                name="uniq_import_idempotency_key",
            )
        ]
        indexes = [
            models.Index(fields=["file_sha256"], name="idx_import_file_sha"),
            models.Index(fields=["status", "created_at"], name="idx_import_status_created"),
        ]


class ImportRowError(models.Model):
    id = models.BigAutoField(primary_key=True)
    job = models.ForeignKey(ImportJob, related_name="row_errors", on_delete=models.CASCADE)
    source_row = models.CharField(max_length=64, blank=True)
    physical_line = models.PositiveIntegerField(null=True, blank=True)
    identity_key = models.CharField(max_length=255, blank=True)
    code = models.CharField(max_length=64)
    field = models.CharField(max_length=64, blank=True)
    message = models.TextField()
    raw_row = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["job", "source_row"], name="idx_row_error_job_source_row"),
            models.Index(fields=["code"], name="idx_row_error_code"),
        ]
