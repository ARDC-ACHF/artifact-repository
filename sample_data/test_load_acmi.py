"""ACMI import transport, failure handling, and repository integration."""

import io
import base64
import json
import urllib.error

import pytest

from sample_data import load_acmi


@pytest.fixture(autouse=True)
def credentials(monkeypatch):
    monkeypatch.setenv("API_AUTH_USERNAME", "tester")
    monkeypatch.setenv("API_AUTH_PASSWORD", "test-secret")


@pytest.fixture
def artifact():
    return {
        "@context": "https://linked.art/ns/v1/linked-art.json",
        "id": "https://api.acmi.net.au/works/125569/",
        "type": "VisualItem",
        "_label": "Frog Detective 3: Corruption at Cowboy County",
    }


@pytest.mark.parametrize("args, work_id", [
    ([], 125569),
    (["75517"], 75517),
    (["https://api.acmi.net.au/works/75517/"], 75517),
    (["--work-id", "75517"], 75517),
    (["--work-id", "https://api.acmi.net.au/works/75517/"], 75517),
    (["--uri", "https://api.acmi.net.au/works/75517/?format=json"], 75517),
])
def test_http_import_preserves_payload(monkeypatch, artifact, capsys, args, work_id):
    artifact["id"] = f"https://api.acmi.net.au/works/{work_id}/"
    requests = []

    def urlopen(request, timeout):
        requests.append(request)
        assert timeout == 30
        result = artifact if request.get_method() == "GET" else {
            "id": artifact["id"], "type": artifact["type"],
            "partner": "acmi", "version_created": True,
        }
        return io.BytesIO(json.dumps(result).encode())

    monkeypatch.setattr(load_acmi.urllib.request, "urlopen", urlopen)
    assert load_acmi.main([*args, "--base-url", "http://repository:8000/"]) == 0
    assert requests[0].full_url == f"https://api.acmi.net.au/works/{work_id}/?format=jsonld"
    assert requests[1].full_url == "http://repository:8000/api/v1/artifacts"
    assert json.loads(requests[1].data) == artifact
    assert requests[1].get_header("Content-type") == "application/ld+json"
    assert requests[0].get_header("Authorization") is None
    assert requests[1].get_header("Authorization") == "Basic " + base64.b64encode(b"tester:test-secret").decode()
    assert "acmi" in capsys.readouterr().out


@pytest.mark.parametrize("work", [
    "https://api.acmi.net.au/works/75517",
    "https://api.acmi.net.au/works/75517/?format=jsonld",
    "https://api.acmi.net.au/works/75517/?format=json&format=html#details",
])
def test_work_url_normalises_format(work):
    assert load_acmi.work_url(work) == "https://api.acmi.net.au/works/75517/?format=jsonld"


@pytest.mark.parametrize("args", [
    ["0"], ["--work-id", "-1"], ["not-a-work"],
    ["https://example.com/works/75517/"],
    ["https://api.acmi.net.au/works/"],
    ["https://api.acmi.net.au/creators/75517/"],
    ["75517", "--work-id", "125569"],
])
def test_invalid_arguments_do_not_fetch(args, monkeypatch):
    def unexpected_fetch(work):
        pytest.fail("Invalid input must not fetch a record")

    monkeypatch.setattr(load_acmi, "fetch_work", unexpected_fetch)
    with pytest.raises(SystemExit) as exc:
        load_acmi.main(args)
    assert exc.value.code == 2


@pytest.mark.parametrize("response", [b"not json", b"[]"])
def test_invalid_source_is_not_published(monkeypatch, response, capsys):
    def urlopen(request, timeout):
        assert request.get_method() == "GET"
        return io.BytesIO(response)

    monkeypatch.setattr(load_acmi.urllib.request, "urlopen", urlopen)
    assert load_acmi.main([]) == 1
    assert "Could not fetch ACMI work" in capsys.readouterr().err


def test_repository_rejection_is_reported(monkeypatch, artifact, capsys):
    monkeypatch.setattr(load_acmi, "fetch_work", lambda work_id: artifact)

    def reject(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 422, "Invalid", {}, io.BytesIO(b"validation failed"))

    monkeypatch.setattr(load_acmi.urllib.request, "urlopen", reject)
    assert load_acmi.main([]) == 1
    assert "HTTP 422: validation failed" in capsys.readouterr().err


def test_direct_import_is_searchable_and_idempotent(tmp_path, artifact):
    from app.index import FtsIndex

    first = load_acmi.publish_direct(artifact, tmp_path)
    second = load_acmi.publish_direct(artifact, tmp_path)
    assert first["partner"] == "acmi"
    assert first["version_created"] is True
    assert second["version_created"] is False
    index = FtsIndex(tmp_path / "index.sqlite3")
    try:
        total, results = index.search("Frog", partners=["acmi"])
        assert total == 1
        assert results[0].iri == artifact["id"]
    finally:
        index.close()


@pytest.mark.parametrize("variable", ["API_AUTH_USERNAME", "API_AUTH_PASSWORD"])
def test_missing_credentials_fail_before_fetch(variable, monkeypatch, capsys):
    monkeypatch.delenv(variable)
    monkeypatch.setattr(load_acmi, "fetch_work", lambda work: pytest.fail("must not fetch"))
    assert load_acmi.main([]) == 1
    assert "Set API_AUTH_USERNAME" in capsys.readouterr().err


def test_direct_mode_needs_no_http_credentials(tmp_path, artifact, monkeypatch):
    monkeypatch.delenv("API_AUTH_USERNAME")
    monkeypatch.delenv("API_AUTH_PASSWORD")
    monkeypatch.setattr(load_acmi, "fetch_work", lambda work: artifact)
    assert load_acmi.main(["--direct", "--data-dir", str(tmp_path)]) == 0


@pytest.mark.parametrize("password, expected", [("test-secret", 0), ("wrong-password", 1)])
def test_loader_against_authenticated_api(tmp_path, artifact, monkeypatch, capsys, password, expected):
    from fastapi.testclient import TestClient
    from app.auth import BasicAuthProvider
    from app.main import create_app

    monkeypatch.setenv("API_AUTH_PASSWORD", password)
    monkeypatch.setattr(load_acmi, "fetch_work", lambda work: artifact)
    app = create_app(data_dir=tmp_path, auth_providers=(BasicAuthProvider("tester", "test-secret"),))
    with TestClient(app) as client:
        def urlopen(request, timeout):
            response = client.post(request.full_url, content=request.data, headers=dict(request.header_items()))
            if response.status_code >= 400:
                raise urllib.error.HTTPError(request.full_url, response.status_code, "Error", {}, io.BytesIO(response.content))
            return io.BytesIO(response.content)

        monkeypatch.setattr(load_acmi.urllib.request, "urlopen", urlopen)
        assert load_acmi.main([]) == expected
        if expected == 0:
            assert load_acmi.main([]) == 0
            assert "unchanged (no new version)" in capsys.readouterr().out
            response = client.get("/api/v1/artifacts", auth=("tester", "test-secret"))
            assert response.json()["total"] == 1
        else:
            assert "HTTP 401" in capsys.readouterr().err
