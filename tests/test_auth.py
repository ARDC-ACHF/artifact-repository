"""Authentication boundary and provider contract checks."""

import base64

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.auth import BasicAuthProvider, Principal
from app.main import create_app


@pytest.mark.parametrize("path", [
    "/api/v1/artifacts", "/api/v1/artifacts/item?iri=x",
    "/api/v1/artifacts/version", "/api/v1/artifacts/versions",
    "/api/v1/search?q=test", "/api/v1/artifacts/validate", "/api/future",
])
def test_api_requires_credentials(monkeypatch, tmp_path, path):
    monkeypatch.setenv("API_AUTH_USERNAME", "reviewer")
    monkeypatch.setenv("API_AUTH_PASSWORD", "test-secret")
    with TestClient(create_app(data_dir=tmp_path)) as client:
        response = client.get(path)
    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Basic ")
    assert response.json() == {"detail": "Not authenticated"}
    assert list(tmp_path.iterdir()) == []


def authorization(value):
    return "Basic " + base64.b64encode(value.encode("utf-8")).decode("ascii")


@pytest.mark.parametrize("header", [
    "Basic", "Basic ", "Basic !!!", "Basic /w==", "Bearer token",
    authorization("no-colon"), authorization("reviewer:wrong"),
    authorization("wrong:test-secret"), authorization(":"),
    "Basic " + base64.b64encode(b"reviewer:test-secret").decode() + "!",
])
def test_bad_credentials_are_rejected_before_body_parsing(tmp_path, header):
    app = create_app(data_dir=tmp_path, auth_providers=(BasicAuthProvider("reviewer", "test-secret"),))
    with TestClient(app) as client:
        for path in ["/api/v1/artifacts", "/api/v1/artifacts/validate"]:
            response = client.post(path, content="{", headers={"Authorization": header})
            assert response.status_code == 401
            assert response.json() == {"detail": "Not authenticated"}
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("username,password", [(None, None), ("user", None), (None, "secret"), ("user", " ")])
def test_missing_configuration_fails_closed(monkeypatch, tmp_path, username, password):
    for key, value in [("API_AUTH_USERNAME", username), ("API_AUTH_PASSWORD", password)]:
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    with TestClient(create_app(data_dir=tmp_path)) as client:
        assert client.get("/api/v1/artifacts", auth=("user", "secret")).status_code == 503
        for path in ["/health", "/docs", "/redoc", "/openapi.json"]:
            assert client.get(path).status_code == 200
    assert list(tmp_path.iterdir()) == []


def test_environment_credentials_and_openapi(monkeypatch, tmp_path):
    monkeypatch.setenv("API_AUTH_USERNAME", "reviewer")
    monkeypatch.setenv("API_AUTH_PASSWORD", "test-secret")
    with TestClient(create_app(data_dir=tmp_path)) as client:
        assert client.get("/api/v1/artifacts", auth=("reviewer", "test-secret")).status_code == 200
        schema = client.get("/openapi.json").json()
    assert schema["components"]["securitySchemes"] == {"Basic": {"type": "http", "scheme": "basic"}}
    assert "security" not in schema["paths"]["/health"]["get"]
    for path, operations in schema["paths"].items():
        if path.startswith("/api/"):
            for operation in operations.values():
                assert operation["security"] == [{"Basic": []}]
                assert {"401", "503"} <= operation["responses"].keys()
    assert "test-secret" not in str(schema)


def test_identity_utf8_and_case_insensitive_scheme():
    provider = BasicAuthProvider("réviewer", "sëcret:with:colons")
    app = create_app(auth_providers=(provider,))

    @app.get("/api/identity")
    def identity(request: Request):
        return vars(request.state.principal)

    with TestClient(app) as client:
        response = client.get("/api/identity", headers={
            "Authorization": authorization("réviewer:sëcret:with:colons").replace("Basic", "bAsIc")
        })
    assert response.json() == {"subject": "réviewer", "method": "Basic"}
    assert "sëcret" not in repr(provider)


def test_multiple_providers_and_no_fallback():
    class TestTokenProvider:
        scheme = "Bearer"
        challenge = "Bearer"
        openapi_scheme = {"type": "http", "scheme": "bearer"}

        async def authenticate(self, credentials):
            return Principal("token-user", self.scheme) if credentials == "test-token" else None

    app = create_app(auth_providers=(BasicAuthProvider("user", "secret"), TestTokenProvider()))

    @app.get("/api/identity")
    def identity(request: Request):
        return vars(request.state.principal)

    with TestClient(app) as client:
        assert client.get("/api/identity", auth=("user", "secret")).json()["method"] == "Basic"
        assert client.get("/api/identity", headers={"Authorization": "Bearer test-token"}).json() == {
            "subject": "token-user", "method": "Bearer"
        }
        assert client.get("/api/identity", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert client.get("/api/identity", headers=[
            ("Authorization", authorization("user:secret")), ("Authorization", "Bearer test-token")
        ]).status_code == 401
        schema = client.get("/openapi.json").json()
        assert schema["paths"]["/api/identity"]["get"]["security"] == [{"Basic": []}, {"Bearer": []}]


def test_empty_providers_and_duplicate_schemes():
    with TestClient(create_app(auth_providers=())) as client:
        assert client.get("/api/v1/artifacts").status_code == 503
    with pytest.raises(ValueError, match="unique"):
        create_app(auth_providers=(BasicAuthProvider("one", "secret"), BasicAuthProvider("two", "secret")))


@pytest.mark.parametrize("username,password", [("", "secret"), ("user", ""), ("u:ser", "secret")])
def test_invalid_provider_configuration(username, password):
    with pytest.raises(ValueError):
        BasicAuthProvider(username, password)


@pytest.mark.parametrize("path", ["/api", "/api/v1/artifacts/", "/%61pi/v1/artifacts"])
def test_path_variants_and_mounted_root(path):
    app = create_app(auth_providers=(BasicAuthProvider("user", "secret"),))
    with TestClient(app, root_path="/repository") as client:
        assert client.get(path, follow_redirects=False).status_code == 401
        assert client.get("/repository/api/v1/artifacts", follow_redirects=False).status_code == 401