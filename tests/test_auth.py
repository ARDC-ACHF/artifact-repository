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


PUBLIC_READ_PATHS = [
    "/api/v1/search?q=Godot", "/api/v1/artifacts", "/api/v1/artifacts/item?iri=https://example.org/x",
    "/api/v1/artifacts/version?iri=https://example.org/x&published_at=2020-01-01T00:00:00Z",
    "/api/v1/artifacts/versions?iri=https://example.org/x",
]


@pytest.mark.parametrize("providers", [(), (BasicAuthProvider("user", "secret"),)])
@pytest.mark.parametrize("path", PUBLIC_READ_PATHS)
def test_public_read_allows_anonymous_get(tmp_path, providers, path):
    app = create_app(data_dir=tmp_path, auth_providers=providers, public_read=True, frontend_dir=None)
    with TestClient(app) as client:
        response = client.get(path)
    assert response.status_code not in {401, 403, 503}
    # Reached the route handler: success, not-found or parameter validation, never an auth response.
    assert response.status_code in {200, 404, 422}
    assert "www-authenticate" not in response.headers


def test_public_read_principal_and_bad_credentials_ignored(tmp_path):
    app = create_app(data_dir=tmp_path, auth_providers=(), public_read=True, frontend_dir=None)
    with TestClient(app) as client:
        assert client.get("/api/v1/search?q=x").json()["results"] == []
        assert client.get("/api/v1/artifacts", headers={"Authorization": "Basic !!!"}).status_code == 200


@pytest.mark.parametrize("providers,expected", [((), 503), ((BasicAuthProvider("user", "secret"),), 401)])
def test_public_read_still_blocks_writes_and_other_paths(tmp_path, providers, expected):
    app = create_app(data_dir=tmp_path, auth_providers=providers, public_read=True, frontend_dir=None)

    @app.get("/api/v1/admin")
    def admin():
        return {"ok": True}

    with TestClient(app) as client:
        assert client.post("/api/v1/artifacts", content="{}").status_code == expected
        assert client.post("/api/v1/artifacts/validate", content="{}").status_code == expected
        assert client.delete("/api/v1/artifacts/item?iri=x").status_code == expected
        assert client.delete("/api/v1/artifacts/version?iri=x&published_at=y").status_code == expected
        assert client.put("/api/v1/artifacts").status_code == expected
        assert client.options("/api/v1/artifacts").status_code == expected
        for path in ["/api/v1/admin", "/api/v1/artifacts/", "/api/v1/search/", "/api/v1/artifacts/validate",
                     "/api/v1/artifacts/item/extra", "/api/v2/search", "/api", "/api/v1"]:
            assert client.get(path, follow_redirects=False).status_code == expected, path


@pytest.mark.parametrize("value,expected", [(None, 503), ("0", 503), ("", 503), ("no", 503), ("1", 200), ("true", 200)])
def test_public_read_environment_flag(monkeypatch, tmp_path, value, expected):
    monkeypatch.delenv("API_AUTH_USERNAME", raising=False)
    monkeypatch.delenv("API_AUTH_PASSWORD", raising=False)
    if value is None:
        monkeypatch.delenv("DEMO_PUBLIC_READ", raising=False)
    else:
        monkeypatch.setenv("DEMO_PUBLIC_READ", value)
    with TestClient(create_app(data_dir=tmp_path, frontend_dir=None)) as client:
        assert client.get("/api/v1/artifacts").status_code == expected
        assert client.post("/api/v1/artifacts", content="{}").status_code == 503


def test_public_read_explicit_false_overrides_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_PUBLIC_READ", "1")
    app = create_app(data_dir=tmp_path, auth_providers=(BasicAuthProvider("user", "secret"),),
                     public_read=False, frontend_dir=None)
    with TestClient(app) as client:
        assert client.get("/api/v1/artifacts").status_code == 401


def test_public_read_openapi_marks_reads_optional(tmp_path):
    app = create_app(data_dir=tmp_path, auth_providers=(BasicAuthProvider("user", "secret"),),
                     public_read=True, frontend_dir=None)
    with TestClient(app) as client:
        paths = client.get("/openapi.json").json()["paths"]
    assert paths["/api/v1/search"]["get"]["security"] == [{"Basic": []}, {}]
    assert paths["/api/v1/artifacts"]["post"]["security"] == [{"Basic": []}]
    assert paths["/api/v1/artifacts/item"]["delete"]["security"] == [{"Basic": []}]


@pytest.fixture
def frontend_dist(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><div id=root></div>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("top secret", encoding="utf-8")
    return dist


def test_frontend_served_without_masking_api(tmp_path, frontend_dist):
    app = create_app(data_dir=tmp_path / "data", auth_providers=(BasicAuthProvider("user", "secret"),),
                     public_read=True, frontend_dir=frontend_dist)
    with TestClient(app) as client:
        for path in ["/", "/artifact?iri=https://example.org/x", "/some/client/route"]:
            response = client.get(path)
            assert response.status_code == 200
            assert "id=root" in response.text
        assert client.get("/assets/app.js").text == "console.log(1)"
        assert client.head("/").status_code == 200
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/docs").status_code == 200
        assert client.get("/redoc").status_code == 200
        assert "/{full_path}" not in client.get("/openapi.json").json()["paths"]
        assert client.get("/api/v1/artifacts").status_code == 200
        assert client.post("/api/v1/artifacts", content="{}").status_code == 401
        assert client.get("/api/v1/unknown", auth=("user", "secret")).status_code == 404
        assert client.get("/api/v1/unknown", auth=("user", "secret")).headers["content-type"] == "application/json"
        for path in ["/docs/extra", "/openapi.json/x", "/health/x"]:
            assert client.get(path).status_code == 404
        for path in ["/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt"]:
            assert "top secret" not in client.get(path).text


def test_create_app_does_not_install_frontend_by_default(tmp_path, monkeypatch):
    import app.main as main
    monkeypatch.setattr(main, "DEFAULT_FRONTEND_DIR", tmp_path / "never-used")
    with TestClient(create_app(data_dir=tmp_path / "data", auth_providers=())) as client:
        assert client.get("/").status_code == 404
        assert all(getattr(route, "path", "") != "/{full_path:path}" for route in client.app.router.routes)


def test_frontend_does_not_shadow_routes_added_later(frontend_dist):
    app = create_app(auth_providers=(BasicAuthProvider("user", "secret"),), frontend_dir=frontend_dist)

    @app.get("/api/identity")
    def identity(request: Request):
        return vars(request.state.principal)

    @app.get("/late")
    def late():
        return {"late": True}

    with TestClient(app) as client:
        assert client.get("/api/identity", auth=("user", "secret")).json() == {"subject": "user", "method": "Basic"}
        assert client.get("/late").json() == {"late": True}
        assert "id=root" in client.get("/other").text


@pytest.mark.parametrize("path", ["/a%00b", "/assets/%00", "/%00/../x"])
def test_frontend_null_byte_path_does_not_crash(tmp_path, frontend_dist, path):
    app = create_app(data_dir=tmp_path / "data", auth_providers=(), frontend_dir=frontend_dist)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(path)
    assert response.status_code == 200
    assert "id=root" in response.text


@pytest.mark.parametrize("with_frontend", [False, True])
@pytest.mark.parametrize("providers", [(), (BasicAuthProvider("user", "secret"),)])
def test_public_read_head_returns_200_without_body(tmp_path, frontend_dist, with_frontend, providers):
    app = create_app(data_dir=tmp_path / "data", auth_providers=providers, public_read=True,
                     frontend_dir=frontend_dist if with_frontend else None)
    with TestClient(app) as client:
        for path in ["/api/v1/search?q=Godot", "/api/v1/artifacts", "/health"]:
            get = client.get(path)
            head = client.head(path)
            assert head.status_code == 200, path
            assert head.content == b""
            assert "www-authenticate" not in head.headers
            assert head.headers["content-type"] == get.headers["content-type"]
            assert head.headers["content-length"] == get.headers["content-length"]
        assert client.head("/api/v1/artifacts/item?iri=https://example.org/missing").status_code == 404
        assert client.head("/api/v1/artifacts/versions?iri=https://example.org/missing").status_code == 404


@pytest.mark.parametrize("with_frontend", [False, True])
def test_head_on_protected_and_unknown_api_paths(tmp_path, frontend_dist, with_frontend):
    app = create_app(data_dir=tmp_path / "data", auth_providers=(BasicAuthProvider("user", "secret"),),
                     public_read=True, frontend_dir=frontend_dist if with_frontend else None)
    with TestClient(app) as client:
        assert client.head("/api/v1/artifacts/validate").status_code == 401
        assert client.head("/api/v1/unknown").status_code == 401
        validate = client.head("/api/v1/artifacts/validate", auth=("user", "secret"))
        assert validate.status_code == 405
        assert "POST" in validate.headers["allow"]
        assert client.get("/api/v1/artifacts/validate", auth=("user", "secret")).status_code == 405
        assert client.head("/api/v1/unknown", auth=("user", "secret")).status_code == 404
        assert client.get("/api/v1/unknown", auth=("user", "secret")).status_code == 404


def test_public_read_head_disabled_still_requires_auth(tmp_path):
    app = create_app(data_dir=tmp_path, auth_providers=(BasicAuthProvider("user", "secret"),), public_read=False)
    with TestClient(app) as client:
        assert client.head("/api/v1/artifacts").status_code == 401
        assert client.head("/api/v1/artifacts", auth=("user", "secret")).status_code == 200


def test_frontend_not_installed_without_index(tmp_path):
    app = create_app(data_dir=tmp_path / "data", auth_providers=(), frontend_dir=tmp_path / "missing")
    with TestClient(app) as client:
        assert client.get("/").status_code == 404
        assert client.get("/health").status_code == 200


@pytest.mark.parametrize("path", ["/api", "/api/v1/artifacts/", "/%61pi/v1/artifacts"])
def test_path_variants_and_mounted_root(path):
    app = create_app(auth_providers=(BasicAuthProvider("user", "secret"),))
    with TestClient(app, root_path="/repository") as client:
        assert client.get(path, follow_redirects=False).status_code == 401
        assert client.get("/repository/api/v1/artifacts", follow_redirects=False).status_code == 401