from django.apps import AppConfig


class CustomerImportServiceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "customer_import_service.db"
    label = "customer_import_service"
    verbose_name = "Customer Import Service"
