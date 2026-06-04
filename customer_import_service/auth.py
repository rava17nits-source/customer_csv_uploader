from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import current_app, g, request
from werkzeug.security import check_password_hash

from customer_import_service.errors import APIError


ROLE_SCOPES = {
    "reader": {"customers:read", "imports:read"},
    "operator": {"customers:read", "customers:write", "imports:read", "imports:write"},
    "admin": {
        "customers:read",
        "customers:write",
        "imports:read",
        "imports:write",
        "admin:read",
    },
}


def scopes_for_roles(roles: list[str]) -> list[str]:
    scopes: set[str] = set()
    for role in roles:
        scopes.update(ROLE_SCOPES.get(role, set()))
    return sorted(scopes)


def issue_token(username: str, roles: list[str]) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "roles": roles,
        "scopes": scopes_for_roles(roles),
        "iss": current_app.config["JWT_ISSUER"],
        "aud": current_app.config["JWT_AUDIENCE"],
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=current_app.config["JWT_TTL_SECONDS"])).timestamp()),
    }
    return jwt.encode(payload, current_app.config["JWT_SECRET"], algorithm="HS256")


def authenticate_credentials(username: str, password: str) -> dict:
    users = current_app.config["SERVICE_USERS"]
    user = users.get(username)
    if not user or not check_password_hash(user.get("password_hash", ""), password):
        raise APIError(401, "invalid_credentials", "Username or password is invalid.")
    roles = user.get("roles", [])
    return {"username": username, "roles": roles, "scopes": scopes_for_roles(roles)}


def current_claims(required_scopes: tuple[str, ...] = ()) -> dict:
    if current_app.config.get("AUTH_DISABLED"):
        claims = {
            "sub": "auth-disabled",
            "roles": ["admin"],
            "scopes": scopes_for_roles(["admin"]),
        }
        g.auth = claims
        return claims

    auth_header = request.headers.get("Authorization", "")
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise APIError(401, "missing_bearer_token", "A bearer token is required.")

    try:
        claims = jwt.decode(
            token,
            current_app.config["JWT_SECRET"],
            algorithms=["HS256"],
            issuer=current_app.config["JWT_ISSUER"],
            audience=current_app.config["JWT_AUDIENCE"],
        )
    except jwt.ExpiredSignatureError as exc:
        raise APIError(401, "token_expired", "The bearer token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise APIError(401, "invalid_token", "The bearer token is invalid.") from exc

    granted_scopes = set(claims.get("scopes", []))
    missing = [scope for scope in required_scopes if scope not in granted_scopes]
    if missing:
        raise APIError(403, "insufficient_scope", "The token does not grant the required scope.", {"missing": missing})

    g.auth = claims
    return claims


def require_scopes(*scopes: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            current_claims(scopes)
            return fn(*args, **kwargs)

        return wrapper

    return decorator
