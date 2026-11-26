import sqlite3
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from app.core.config import ROOT, Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, persistent_data_dir=tmp_path, database_path=tmp_path / "test.sqlite3")


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_PORT", "8888")
    monkeypatch.setenv("APP_TIMEZONE", "UTC")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "custom.sqlite3"))
    settings = Settings(_env_file=None)
    assert (settings.app_port, settings.app_timezone, settings.sqlite_path) == (
        8888, "UTC", tmp_path / "custom.sqlite3"
    )
    monkeypatch.setenv("APP_TIMEZONE", "Invalid/Timezone")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_startup_migration_and_health(client, settings):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"data": {"status": "ok", "database": "available"}}
    connection = sqlite3.connect(settings.sqlite_path)
    try:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == ("0004",)
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )}
        assert {"alembic_version", "administrator", "administrator_session",
                "dashboard_settings", "task", "deadline"} <= tables
    finally:
        connection.close()


def test_repeat_startup_preserves_data(settings):
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/health").status_code == 200
        with client.app.state.database.engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE retained (value INTEGER)")
            connection.exec_driver_sql("INSERT INTO retained VALUES (42)")
    with TestClient(create_app(settings)) as client:
        with client.app.state.database.engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT value FROM retained").scalar_one() == 42


def test_database_failure(client, monkeypatch):
    def fail():
        raise OperationalError("SELECT 1", {}, Exception("test database unavailable"))

    monkeypatch.setattr(client.app.state.database, "sessions", fail)
    response = client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.json() == {"data": {"status": "degraded", "database": "unavailable"}}


def test_error_envelope(client):
    response = client.get("/api/v1/unknown")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http_404"


def test_kindle_image(client):
    response = client.get("/api/kindle/image.png")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "no-store"
    with Image.open(BytesIO(response.content)) as image:
        assert (image.format, image.mode, image.size) == ("PNG", "L", (758, 1024))
        assert image.getextrema() == (0, 255)


def test_kindle_page(client):
    response = client.get("/kindle")
    assert response.status_code == 200
    assert 'src="/api/kindle/image.png"' in response.text
    assert "<script" not in response.text


@pytest.mark.skipif(not (ROOT / "frontend/dist/index.html").is_file(), reason="Build frontend first")
def test_built_frontend(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "<title>Kindle Dashboard</title>" in response.text
    for asset in (ROOT / "frontend/dist/assets").iterdir():
        assert client.get(f"/assets/{asset.name}").status_code == 200


def test_kindle_diagnostic(client):
    page = client.get("/kindle/test")
    assert page.status_code == 200
    assert page.headers["cache-control"] == "no-store"
    assert 'http-equiv="refresh" content="30"' in page.text
    assert 'id="server-time"' in page.text
    assert 'id="last-press">None yet<' in page.text
    assert '<form method="post" action="/kindle/test">' in page.text
    assert '<form method="get" action="/kindle/test">' in page.text
    assert 'src="/api/kindle/image.png"' in page.text
    assert "<script" not in page.text

    press = client.post("/kindle/test", follow_redirects=False)
    assert press.status_code == 303
    assert press.headers["location"] == "/kindle/test"

    last_press = client.app.state.kindle_diagnostic_last_press
    assert last_press
    for _ in range(2):
        assert f'id="last-press">{last_press}<' in client.get(press.headers["location"]).text

    assert 'id="last-press"' not in client.get("/kindle").text


def test_kindle_diagnostic_state_is_app_local(client, settings):
    client.post("/kindle/test")
    with TestClient(create_app(settings)) as other_client:
        assert 'id="last-press">None yet<' in other_client.get("/kindle/test").text
