from flask import Flask
from flask_ext.restful import Api

from customer_import_service.config import Config
from customer_import_service.db import configure_django, migrate_database
from customer_import_service.errors import register_error_handlers
from customer_import_service.observability import configure_logging, register_observability


def create_app(overrides: dict | None = None) -> Flask:
    configure_django()
    app = Flask(__name__)
    app.config.from_object(Config)
    if overrides:
        app.config.update(overrides)

    configure_logging(app)
    if app.config.get("AUTO_MIGRATE"):
        migrate_database(verbosity=0)

    register_observability(app)
    register_error_handlers(app)

    from customer_import_service.resources import (
        AuthTokenResource,
        CustomerListResource,
        CustomerResource,
        ImportCollectionResource,
        ImportErrorsResource,
        ImportJobResource,
        ImportRetryResource,
    )

    api = Api(app, catch_all_404s=True)
    api.add_resource(AuthTokenResource, "/v1/auth/token")
    api.add_resource(CustomerListResource, "/v1/customers")
    api.add_resource(CustomerResource, "/v1/customers/<string:customer_id>")
    api.add_resource(ImportCollectionResource, "/v1/imports")
    api.add_resource(ImportJobResource, "/v1/imports/<string:job_id>")
    api.add_resource(ImportErrorsResource, "/v1/imports/<string:job_id>/errors")
    api.add_resource(ImportRetryResource, "/v1/imports/<string:job_id>/retry")
    return app


app = create_app()
