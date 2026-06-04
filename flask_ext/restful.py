"""Small compatibility shim around Flask-RESTful.

The current package name is ``flask_restful``. This module lets the service use
the older ``flask_ext.restful`` import style requested for the exercise while
still depending on the maintained extension package.
"""

from flask import jsonify
from flask_restful import Api as FlaskRestfulApi
from flask_restful import Resource, abort, fields, marshal, marshal_with, reqparse


class Api(FlaskRestfulApi):
    def handle_error(self, error):
        from customer_import_service.errors import APIError, error_payload

        if isinstance(error, APIError):
            return jsonify(error_payload(error.status_code, error.code, error.message, error.details)), error.status_code

        return super().handle_error(error)

__all__ = ["Api", "Resource", "abort", "fields", "marshal", "marshal_with", "reqparse"]
