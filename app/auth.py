"""API authentication boundary with replaceable, scheme-specific providers."""

import base64
import binascii
from dataclasses import dataclass, field
import os
import secrets
from typing import Protocol

from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse


@dataclass(frozen=True)
class Principal:
    subject: str
    method: str


class AuthenticationProvider(Protocol):
    scheme: str
    challenge: str
    openapi_scheme: dict

    async def authenticate(self, credentials: str) -> Principal | None:
        """Return a verified identity, or None for invalid credentials."""
        ...


@dataclass(frozen=True)
class BasicAuthProvider:
    username: str = field(repr=False)
    password: str = field(repr=False)
    scheme = "Basic"
    challenge = 'Basic realm="repository", charset="UTF-8"'
    openapi_scheme = {"type": "http", "scheme": "basic"}

    def __post_init__(self):
        if not self.username.strip() or ":" in self.username or not self.password.strip():
            raise ValueError("Basic authentication requires a username without ':' and a nonblank password")

    async def authenticate(self, credentials: str) -> Principal | None:
        try:
            decoded = base64.b64decode(credentials, validate=True).decode("utf-8")
            username, password = decoded.split(":", 1)
        except (ValueError, binascii.Error, UnicodeError):
            return None
        username_matches = secrets.compare_digest(username.encode("utf-8"), self.username.encode("utf-8"))
        password_matches = secrets.compare_digest(password.encode("utf-8"), self.password.encode("utf-8"))
        if username_matches & password_matches:
            return Principal(self.username, self.scheme)
        return None


def providers_from_environment() -> tuple[AuthenticationProvider, ...]:
    username = os.environ.get("API_AUTH_USERNAME", "")
    password = os.environ.get("API_AUTH_PASSWORD", "")
    if not username.strip() or not password.strip():
        return ()
    return (BasicAuthProvider(username, password),)


def is_api_path(path: str) -> bool:
    return path == "/api" or path.startswith("/api/")


class APIAuthenticationMiddleware:
    def __init__(self, app, providers: tuple[AuthenticationProvider, ...]):
        self.app = app
        self.providers = {provider.scheme.lower(): provider for provider in providers}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        connection = HTTPConnection(scope)
        path = scope["path"]
        root_path = scope.get("root_path", "").rstrip("/")
        if root_path and path.startswith(root_path + "/"):
            path = path[len(root_path):]
        if not is_api_path(path):
            await self.app(scope, receive, send)
            return
        if not self.providers:
            await JSONResponse({"detail": "API authentication is not configured"}, status_code=503)(scope, receive, send)
            return
        headers = connection.headers.getlist("authorization")
        principal = None
        if len(headers) == 1:
            scheme, separator, credentials = headers[0].partition(" ")
            provider = self.providers.get(scheme.lower())
            if provider is not None and separator and credentials:
                principal = await provider.authenticate(credentials)
        if principal is None:
            challenge = ", ".join(provider.challenge for provider in self.providers.values())
            await JSONResponse(
                {"detail": "Not authenticated"}, status_code=401,
                headers={"WWW-Authenticate": challenge},
            )(scope, receive, send)
            return
        scope.setdefault("state", {})["principal"] = principal
        await self.app(scope, receive, send)


def install_authentication(app, providers: tuple[AuthenticationProvider, ...]):
    schemes = [provider.scheme.lower() for provider in providers]
    if len(schemes) != len(set(schemes)):
        raise ValueError("Authentication provider schemes must be unique")
    app.add_middleware(APIAuthenticationMiddleware, providers=providers)
    original_openapi = app.openapi

    def openapi():
        schema = original_openapi()
        definitions = {provider.scheme: provider.openapi_scheme for provider in providers}
        if not definitions:
            definitions = {"Basic": BasicAuthProvider.openapi_scheme}
        schema.setdefault("components", {}).setdefault("securitySchemes", {}).update(definitions)
        for path, operations in schema["paths"].items():
            if is_api_path(path):
                for method, operation in operations.items():
                    if method in {"get", "post", "put", "patch", "delete", "head", "options", "trace"}:
                        operation["security"] = [{name: []} for name in definitions]
                        operation["responses"].update({
                            "401": {"description": "Missing or invalid credentials"},
                            "503": {"description": "API authentication is not configured"},
                        })
        return schema

    app.openapi = openapi