import pytest
from fastapi.testclient import TestClient

from backend.config import load_settings
from backend.main import create_app

pytestmark = pytest.mark.integration


@pytest.fixture
def client(tmp_path, clean_logging):
    settings = load_settings()
    settings.logging.file = tmp_path / "api.log"
    with TestClient(create_app(settings)) as c:
        yield c, tmp_path / "api.log"


def test_health_ok(client):
    c, _ = client
    r = c.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["radio_backend_preference"] == "auto"


def test_health_env_reports_packages(client):
    c, _ = client
    body = c.get("/health/env").json()
    assert body["python"].startswith("3.12")
    assert "sionna-rt" in body["packages"]


def test_unknown_route_is_404(client):
    c, _ = client
    assert c.get("/does-not-exist").status_code == 404


def test_openapi_and_docs_are_generated(client):
    c, _ = client
    schema = c.get("/openapi.json").json()
    assert "/health" in schema["paths"]
    assert c.get("/docs").status_code == 200


def test_startup_is_logged(client):
    c, log_file = client
    c.get("/health")
    assert "startup" in log_file.read_text()
