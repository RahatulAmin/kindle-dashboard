import json
import sqlite3
from datetime import datetime, timedelta
from io import BytesIO
from time import time
from urllib.parse import parse_qs, urlsplit

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app.core.config import ROOT, Settings
from app.main import create_app
from app.models.dashboard import Admin, AdminSession
from app.schemas.dashboard import Preferences, WeatherLocation
from app.services import weather
from app.services.dashboard import TORONTO, days_until
from app.setup_admin import create_admin

CREDENTIALS = {"username": "test-admin", "password": "a temporary test password"}
LOGIN = {"X-Kindle-Admin": "1"}


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, database_path=tmp_path / "phase2.sqlite3")


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings), base_url="https://testserver") as browser:
        yield browser


def sign_in(client):
    response = client.post("/api/v1/auth/login", json=CREDENTIALS, headers=LOGIN)
    assert response.status_code == 200
    return response, {"X-CSRF-Token": response.json()["data"]["csrf_token"]}


@pytest.fixture
def admin(client):
    create_admin(client.app.state.database, **CREDENTIALS)
    _, csrf = sign_in(client)
    return csrf


def test_setup_login_csrf_logout(client):
    assert client.get("/api/v1/auth/session").json()["data"]["setup_required"]
    assert client.get("/api/v1/tasks").status_code == 401
    assert client.post("/api/v1/tasks", json={"title": "unauthorized"}).status_code == 401
    create_admin(client.app.state.database, **CREDENTIALS)
    with pytest.raises(ValueError, match="already exists"):
        create_admin(client.app.state.database, **CREDENTIALS)
    with client.app.state.database.sessions() as db:
        assert db.get(Admin, 1).password_hash != CREDENTIALS["password"]
    assert client.post("/api/v1/auth/login", json=CREDENTIALS).status_code == 403
    response, csrf = sign_in(client)
    cookie = response.headers["set-cookie"].lower()
    assert all(flag in cookie for flag in ("secure", "httponly", "samesite=strict", "max-age="))
    assert client.get("/api/v1/tasks").status_code == 200
    assert client.post("/api/v1/tasks", json={"title": "missing CSRF"}).status_code == 403
    assert client.post("/api/v1/tasks", json={"title": "wrong CSRF"},
                       headers={"X-CSRF-Token": "bad"}).status_code == 403
    assert client.post("/api/v1/auth/logout", headers=csrf).status_code == 204
    assert client.get("/api/v1/settings").status_code == 401


def test_session_expiration(client, admin):
    with client.app.state.database.sessions() as db:
        db.scalar(select(AdminSession)).expires_at = int(time()) - 1
        db.commit()
    assert client.get("/api/v1/deadlines").status_code == 401
    assert client.get("/api/v1/auth/session").json()["data"]["administrator"] is None


def test_login_rate_limit(client):
    wrong = {**CREDENTIALS, "password": "wrong"}
    for _ in range(5):
        assert client.post("/api/v1/auth/login", json=wrong, headers=LOGIN).status_code == 401
    response = client.post("/api/v1/auth/login", json=wrong, headers=LOGIN)
    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"


def data(response, status=200):
    assert response.status_code == status, response.text
    return response.json()["data"]


def test_tasks_and_preferences_persist(client, admin, settings):
    assert data(client.get("/api/v1/tasks")) == []
    first = {"title": "Pack lunch", "position": 20, "due_date": "2099-01-15"}
    item = data(client.post("/api/v1/tasks", headers=admin, json=first), 201)
    other = data(client.post("/api/v1/tasks", headers=admin, json={
        "title": "Check storage", "position": 0,
    }), 201)
    assert [task["id"] for task in data(client.get("/api/v1/tasks"))] == [other["id"], item["id"]]
    url = f"/api/v1/tasks/{item['id']}"
    changed = data(client.put(url, headers=admin, json={
        **first, "title": "Pack dinner", "priority": "high", "completed": True, "kindle_visible": False,
    }))
    assert changed["created_at"] == item["created_at"]
    assert changed["updated_at"] > item["updated_at"]
    assert client.delete(f"/api/v1/tasks/{other['id']}", headers=admin).status_code == 204
    assert client.delete(f"/api/v1/tasks/{other['id']}", headers=admin).status_code == 404
    prefs = data(client.get("/api/v1/settings"))
    prefs["widgets"].reverse()
    prefs["widgets"][0]["visible"] = True
    prefs["dashboard_title"] = "Home dashboard"
    assert data(client.put("/api/v1/settings", headers=admin, json=prefs)) == prefs
    assert client.put("/api/v1/settings", headers=admin, json={**prefs, "widgets": []}).status_code == 422

    with TestClient(create_app(settings), base_url="https://testserver", cookies=client.cookies) as restarted:
        assert data(restarted.get("/api/v1/tasks")) == [changed]
        assert data(restarted.get("/api/v1/settings")) == prefs
        assert data(restarted.get("/api/v1/overview")) == {"open_tasks": 0, "active_deadlines": 0}


def test_deadlines_chronology_calendar_and_edit(client, admin):
    today = datetime.now(TORONTO).date()
    tomorrow = (today + timedelta(days=1)).isoformat()
    records = [
        {"title": "Tomorrow", "due_date": tomorrow},
        {"title": "Today no time", "due_date": today.isoformat()},
        {"title": "Today morning", "due_date": today.isoformat(), "due_time": "08:00"},
    ]
    entries = [data(client.post("/api/v1/deadlines", json=item, headers=admin), 201) for item in records]
    sorted_rows = data(client.get("/api/v1/deadlines"))
    assert [row["id"] for row in sorted_rows] == [entries[2]["id"], entries[1]["id"], entries[0]["id"]]
    assert [row["days_until"] for row in sorted_rows] == [0, 0, 1]
    assert days_until(today, today + timedelta(days=1)) == -1
    url = f"/api/v1/deadlines/{entries[0]['id']}"
    changed = data(client.put(url, json={**records[0], "completed": True, "archived": True}, headers=admin))
    assert changed["completed"] and changed["archived"]
    assert client.delete(url, headers=admin).status_code == 204


def test_weather_cache_and_outage(monkeypatch):
    now = [100.0]
    calls = []
    fail = [False]
    monkeypatch.setattr(weather, "monotonic", lambda: now[0])

    def fetch(location):
        calls.append(location)
        if fail[0]:
            raise OSError("offline")
        return weather.Weather("fresh", -2, "Overcast", 2, -5, "2026-11-22T12:00:00+00:00")

    monkeypatch.setattr(weather, "fetch_weather", fetch)
    cache = weather.WeatherCache()
    location = WeatherLocation()
    assert cache.get(location).status == "fresh"
    now[0] += 899
    assert cache.get(location).status == "fresh"
    assert len(calls) == 1
    fail[0] = True
    now[0] += 1
    stale = cache.get(location)
    assert (stale.status, stale.temperature, stale.updated_at) == ("stale", -2, "2026-11-22T12:00:00+00:00")
    assert cache.get(location) == stale
    assert len(calls) == 2
    assert weather.WeatherCache().get(location).status == "unavailable"
    now[0] += 61
    fail[0] = False
    assert cache.get(location).status == "fresh"


def test_open_meteo_response(monkeypatch):
    def download(url, timeout):
        assert urlsplit(url).hostname == "api.open-meteo.com"
        assert parse_qs(urlsplit(url).query)["timezone"] == ["America/Toronto"]
        assert timeout == 4
        return BytesIO(json.dumps({
            "current": {"temperature_2m": -2.1, "weather_code": 73},
            "daily": {"temperature_2m_max": [0.5], "temperature_2m_min": [-4.5]},
        }).encode())

    monkeypatch.setattr(weather, "urlopen", download)
    result = weather.fetch_weather(WeatherLocation())
    assert (result.temperature, result.condition, result.high, result.low) == (-2.1, "Snow", 0.5, -4.5)
    assert result.updated_at


def test_kindle_real_data_and_diagnostic(client, admin, monkeypatch):
    import app.api.kindle_display as display

    assert client.get("/api/kindle/dashboard.png").status_code == 404
    assert "/api/kindle/image.png" in client.get("/kindle").text
    assert client.post("/kindle/test", follow_redirects=False).status_code == 303
    assert "None yet" not in client.get("/kindle/test").text
    prefs = Preferences(kindle_data_enabled=True, dashboard_title="Dashboard NAS")
    prefs.widgets[2].limit = 12
    prefs.widgets[3].limit = 12
    data(client.put("/api/v1/settings", headers=admin, json=prefs.model_dump()))
    for index in range(13):
        label = f"{index} " + "W" * 150
        data(client.post("/api/v1/tasks", headers=admin, json={
            "title": label, "kindle_visible": index != 0, "position": index,
        }), 201)
        data(client.post("/api/v1/deadlines", headers=admin, json={
            "title": label, "due_date": "2099-01-15", "archived": index == 0,
        }), 201)

    def render(settings, config, tasks, deadlines, forecast):
        assert len(tasks) == len(deadlines) == 12
        assert all(not record.title.startswith("0 ") for record in [*tasks, *deadlines])
        assert forecast.temperature == -3
        return original(settings, config, tasks, deadlines, forecast)

    original = display.render_dashboard
    monkeypatch.setattr(display, "render_dashboard", render)
    monkeypatch.setattr(weather, "fetch_weather", lambda _: weather.Weather("fresh", -3, "Snow", 0, -5))
    client.cookies.clear()
    page = client.get("/kindle")
    assert 'http-equiv="refresh" content="30"' in page.text and "<script" not in page.text
    image = client.get("/api/kindle/dashboard.png")
    assert image.status_code == 200 and image.headers["cache-control"] == "no-store"
    with Image.open(BytesIO(image.content)) as png:
        assert png.size == (758, 1024) and png.mode == "L"
        left, top, right, bottom = png.point(lambda x: 255 - x).getbbox()
        assert left > 0 and top > 0 and right < 758 and bottom < 1024
    assert client.get("/api/v1/tasks").status_code == 401
    assert "/api/kindle/image.png" in client.get("/kindle/test").text


def test_upgrade_from_baseline_preserves_database(settings, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(settings.sqlite_path))
    config = Config(str(ROOT / "backend/alembic.ini"))
    command.upgrade(config, "0001")
    with sqlite3.connect(settings.sqlite_path) as db:
        db.execute("CREATE TABLE legacy (contents TEXT)")
        db.execute("INSERT INTO legacy VALUES ('keep this')")
    with TestClient(create_app(settings)) as app:
        assert app.get("/api/v1/auth/session").json()["data"]["setup_required"]
    with sqlite3.connect(settings.sqlite_path) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("0002",)
        assert db.execute("SELECT contents FROM legacy").fetchone() == ("keep this",)
