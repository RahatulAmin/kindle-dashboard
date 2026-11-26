import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from io import BytesIO
import json
from secrets import token_urlsafe
from threading import Barrier

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api import kindle_landscape
from app.api_tokens import create_token
from app.core.config import Settings
from app.db.database import BACKEND, Database
from app.main import create_app
from app.models.assistant import ApiAudit, ApiToken
from app.models.dashboard import Task
from app.rendering.landscape_layout import HEIGHT, LEFT, PANEL_X, PRAYER_Y, WIDTH
from app.schemas.dashboard import Preferences
from app.services import entry_sync
from app.services.assistant import SCOPES, timestamp
from app.services.auth import LoginLimiter, token_digest
from app.services.dashboard import save_preferences
from app.services.prayer_times import PrayerPreferences, save_prayer_preferences
from app.services.weather import Weather
from app.setup_admin import create_admin

DEVICE = {"access-token": token_urlsafe(24)}
PATH = "/api/v1"


@pytest.fixture
def dashboard(tmp_path):
    settings = Settings(_env_file=None, database_path=tmp_path / "dashboard.sqlite3", trmnl_access_token=DEVICE["access-token"])
    app = create_app(settings)
    app.state.weather.get = lambda _: Weather("fresh", 2, "Partly cloudy", 4, -2)
    with TestClient(app, base_url="https://testserver") as client:
        yield app, client


def issue(app, scopes=SCOPES, expiration=None):
    with app.state.database.sessions() as db:
        identifier, raw = create_token(db, "integration test", sorted(scopes), expiration)
    return identifier, {"Authorization": f"Bearer {raw}"}


def admin(dashboard):
    app, client = dashboard
    password = token_urlsafe(24)
    create_admin(app.state.database, "test-admin", password)
    result = client.post(PATH + "/auth/login", headers={"X-Kindle-Admin": "1"},
                         json={"username": "test-admin", "password": password})
    assert result.status_code == 200
    return {"X-CSRF-Token": result.json()["data"]["csrf_token"]}


def test_token_lifecycle_scope_and_cookie_precedence(dashboard):
    app, client = dashboard
    identifier, bearer = issue(app, {"tasks:read"})
    _, expired = issue(app, expiration=timestamp(datetime.now(UTC) - timedelta(seconds=1)))
    revoked_id, revoked = issue(app)
    with app.state.database.sessions() as db:
        db.get(ApiToken, revoked_id).revoked = True
        db.commit()

    assert client.get(PATH + "/tasks").status_code == 401
    assert client.get(PATH + "/tasks", headers=bearer).status_code == 200
    assert client.get(PATH + "/deadlines", headers=bearer).status_code == 403
    assert client.post(PATH + "/tasks", headers=bearer, json={"title": "Denied"}).status_code == 403

    csrf = admin(dashboard)
    assert client.get(PATH + "/tasks").status_code == 200
    assert client.post(PATH + "/tasks", json={"title": "Missing CSRF"}).status_code == 403
    assert client.post(PATH + "/tasks", headers=csrf, json={"title": "Admin"}).json()["data"]["kindle_visible"]
    for denied in (expired, revoked, {"Authorization": "Bearer invalid"}, {"Authorization": "bEaReR"}):
        response = client.get(PATH + "/tasks", headers=denied)
        assert response.status_code == 401 and response.headers["WWW-Authenticate"] == "Bearer"

    for target in ("audit", "settings", "overview", "prayer-times", "auth/session"):
        assert client.get(f"{PATH}/{target}", headers=bearer).status_code == 401
    assert client.delete(PATH + "/briefing", headers={**bearer, **csrf}).status_code == 401
    assert client.get("/api/kindle/landscape/frame", headers=bearer).status_code == 401
    with app.state.database.sessions() as db:
        record = db.get(ApiToken, identifier)
        raw = bearer["Authorization"].split()[1]
        assert record.token_hash == token_digest(raw) and record.last_used_at and raw != record.token_hash
        assert db.scalar(select(func.count()).select_from(ApiAudit)) == 0
    app.state.assistant_limiter = LoginLimiter(per_address=1, total=2)
    assert client.get(PATH + "/tasks", headers=bearer).status_code == 200
    assert client.get(PATH + "/tasks", headers=bearer).headers["Retry-After"] == "60"


@pytest.mark.parametrize("collection", ("tasks", "deadlines"))
def test_crud_filters_and_versions(dashboard, collection):
    app, client = dashboard
    identifier, bearer = issue(app)
    _, writer = issue(app, {f"{collection}:write"})
    endpoint = f"{PATH}/{collection}"
    body = {"title": "Original", "source": "muse", "external_ref": "42", "due_date": "2030-02-04"}
    assert client.post(endpoint, headers=bearer, json={"title": "Partial pair", "source": "muse"}).status_code == 422
    created = client.post(endpoint, headers=bearer, json=body)
    assert created.status_code == 201, created.text
    item = created.json()["data"]
    assert not item["kindle_visible"]
    address = f"{endpoint}/{item['id']}"
    retry = client.post(endpoint, headers=bearer, json=body)
    assert retry.status_code == 200 and retry.json()["data"] == item
    assert client.get(address, headers=bearer).json()["data"] == item
    patch = {"completed": True, "expected_updated_at": item["updated_at"]}
    if collection == "deadlines":
        patch["archived"] = True
    changed = client.put(address, headers=bearer, json=patch).json()["data"]
    assert changed["completed"] and changed["created_at"] == item["created_at"]
    assert client.put(address, headers=bearer, json=patch).json()["data"] == changed
    stale = client.put(address, headers=bearer, json={"title": "Stale", "expected_updated_at": item["updated_at"]})
    assert stale.status_code == 409
    assert stale.headers["Link"] == f'<{address}>; rel="latest-version"'
    assert stale.headers["ETag"].strip('"') == changed["updated_at"]
    filtered = client.get(endpoint, headers=bearer, params={
        "completed": True, "due_from": "2030-02-04", "due_to": "2030-02-04",
        "source": "muse", "external_ref": "42", "updated_since": changed["updated_at"],
    })
    assert filtered.json()["data"] == [changed]
    assert client.get(endpoint, headers=bearer, params={"completed": False}).json()["data"] == []
    assert client.delete(address, headers=writer).status_code == 403

    csrf = admin(dashboard)
    editable = {"title", "description", "priority", "completed", "kindle_visible", "due_date",
                "position", "due_time", "archived"}
    web_edit = {key: value for key, value in changed.items() if key in editable}
    final = client.put(address, headers=csrf, json={
        **web_edit, "title": "Edited by admin", "source": "ignored", "external_ref": "ignored",
    }).json()["data"]
    assert final["source"] == "muse" and final["external_ref"] == "42"
    assert client.delete(address, headers=bearer, params={"expected_updated_at": item["updated_at"]}).status_code == 409
    assert client.delete(address, headers=bearer).status_code == 204
    assert client.get(address, headers=bearer).status_code == 404
    history = client.get(PATH + "/audit", params={"token_id": identifier}).json()["data"]
    assert [row["action"] for row in history] == ["delete", "update", "create"]
    assert client.get(PATH + "/audit", params={"action": "update", "date_from": changed["updated_at"][:10],
                                             "date_to": changed["updated_at"][:10]}).json()["data"] == history[1:2]
    assert "completed" in history[1]["changed_fields"] and "Stale" not in str(history)


@pytest.mark.parametrize("collection", ("tasks", "deadlines"))
def test_concurrent_upserts_and_partial_updates(dashboard, collection):
    app, client = dashboard
    _, bearer = issue(app)
    barrier = Barrier(6)
    endpoint = f"{PATH}/{collection}"
    payload = {"title": "First", "source": "muse", "external_ref": "same",
               "due_date": "2030-02-04", "kindle_visible": True}
    if collection == "tasks":
        payload["position"] = 14

    def send(_):
        barrier.wait(timeout=5)
        response = client.post(endpoint, headers=bearer, json=payload)
        return response.status_code, response.json()["data"]

    with ThreadPoolExecutor(max_workers=6) as pool:
        responses = list(pool.map(send, range(6)))
    assert sorted(code for code, _ in responses) == [200] * 5 + [201]
    original = responses[0][1]
    assert all(row == original for _, row in responses)
    update = client.post(endpoint, headers=bearer,
                         json={"source": "muse", "external_ref": "same", "title": "Partial"}).json()["data"]
    assert update["id"] == original["id"] and update["created_at"] == original["created_at"]
    assert update["due_date"] == original["due_date"] and update["kindle_visible"]
    if collection == "tasks":
        assert update["position"] == 14
    with app.state.database.sessions() as db:
        assert [row.action for row in db.scalars(select(ApiAudit).order_by(ApiAudit.id))] == ["create", "upsert"]


def test_kindle_completion_wins_over_retried_sync(dashboard):
    app, client = dashboard
    _, bearer = issue(app)
    with app.state.database.sessions() as db:
        save_preferences(db, Preferences(kindle_data_enabled=True))
    endpoint = PATH + "/tasks"
    body = {"title": "Check on Kindle", "source": "muse", "external_ref": "k", "completed": False,
            "kindle_visible": True}
    item = client.post(endpoint, headers=bearer, json=body).json()["data"]
    frame = client.get("/api/kindle/landscape/frame", headers=DEVICE).json()
    hit = next(region for region in frame["regions"] if region["action"] == "complete")
    result = client.put(f"/api/kindle/landscape/tasks/{item['id']}/completion", headers=DEVICE,
                        json={field: hit[field] for field in ("completed", "capability")})
    assert result.status_code == 204
    assert client.post(endpoint, headers=bearer, json=body).status_code == 409
    assert client.post(endpoint, headers=bearer,
                       json={"source": "muse", "external_ref": "k", "title": "Still done"}).json()["data"]["completed"]
    address = f"{endpoint}/{item['id']}"
    assert client.put(address, headers=bearer, json={"completed": False}).status_code == 409
    current = client.get(address, headers=bearer).json()["data"]
    assert not client.put(address, headers=bearer,
                          json={"completed": False, "expected_updated_at": current["updated_at"]}).json()["data"]["completed"]


def test_mutation_rolls_back_if_audit_fails(dashboard, monkeypatch):
    app, _ = dashboard
    identifier, bearer = issue(app)
    original = entry_sync.audit

    def invalid_audit(db, token, *args, **kwargs):
        original(db, type(token)(-1, token.name), *args, **kwargs)

    monkeypatch.setattr(entry_sync, "audit", invalid_audit)
    with TestClient(app, base_url="https://testserver", raise_server_exceptions=False) as client:
        assert client.post(PATH + "/tasks", headers=bearer, json={"title": "Rollback"}).status_code == 500
    with app.state.database.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Task)) == 0
        assert db.scalar(select(func.count()).select_from(ApiAudit)) == 0
        assert db.get(ApiToken, identifier).last_used_at is None
        db.add(Task(title="Invalid pair", description="", priority="normal", completed=False,
                    kindle_visible=False, position=0, source="muse"))
        with pytest.raises(IntegrityError):
            db.commit()


def test_briefing_validation_and_landscape_regions(dashboard, monkeypatch):
    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 25, 15, 0, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr(kindle_landscape, "datetime", FixedClock)
    app, client = dashboard
    csrf = admin(dashboard)
    _, bearer = issue(app)
    _, reader = issue(app, {"briefing:read"})
    url = PATH + "/briefing"
    assert client.get(url, headers=bearer).json() == {"data": None}
    assert client.post(url, headers=reader, json={"title": "Denied", "lines": []}).status_code == 403
    for payload in ({"title": "X" * 81, "lines": []}, {"title": "X", "lines": ["Y"] * 7},
                    {"title": "X", "lines": ["Y" * 101]}, {"title": "X", "lines": ["line\nbreak"]}):
        assert client.post(url, headers=bearer, json=payload).status_code == 422
    assert client.post(url, headers=bearer, content=b"x" * 32769).status_code == 413
    with app.state.database.sessions() as db:
        prefs = Preferences(kindle_data_enabled=True)
        save_preferences(db, prefs)
        save_prayer_preferences(db, PrayerPreferences(enabled=True, school=0))
    app.state.prayers.refresh = lambda *_: True
    for index in range(12):
        assert client.post(PATH + "/tasks", headers=csrf, json={"title": f"Task {index}"}).status_code == 201

    def frame(page):
        data = client.get("/api/kindle/landscape/frame", headers=DEVICE, params={"page": page, "number": 2}).json()
        with Image.open(BytesIO(base64.b64decode(data["png"]))) as image:
            assert image.size == (WIDTH, HEIGHT) and image.mode == "L"
            return data["regions"], image.copy()

    initial = {page: frame(page) for page in ("todo", "calendar", "pomodoro")}
    first = client.post(url, headers=bearer, json={"title": "First", "lines": ["Intro"]}).json()["data"]
    payload = {"title": "W" * 80, "lines": [f"{n} " + "W" * 98 for n in range(6)]}
    published = client.post(url, headers=bearer, json=payload).json()["data"]
    assert published["updated_at"] != first["updated_at"]
    assert client.post(url, headers=bearer, json=payload).json()["data"] == published
    assert client.get(url, headers=reader).json()["data"] == published
    assert frame("todo")[1].tobytes() == initial["todo"][1].tobytes()

    for widget in prefs.widgets:
        if widget.key == "briefing":
            widget.visible = True
    assert client.put(PATH + "/settings", headers=csrf, json=prefs.model_dump(mode="json")).status_code == 200
    regions, image = frame("todo")
    initial_regions, original = initial["todo"]
    assert [{k: v for k, v in r.items() if k != "capability"} for r in regions] == [
        {k: v for k, v in r.items() if k != "capability"} for r in initial_regions
    ]
    for bounds in ((0, 0, PANEL_X, HEIGHT), (PANEL_X, 0, WIDTH, 368), (0, PRAYER_Y, WIDTH, HEIGHT)):
        assert image.crop(bounds).tobytes() == original.crop(bounds).tobytes()
    assert image.crop((PANEL_X + 36, 585, WIDTH - 36, PRAYER_Y)).getextrema() == (0, 255)
    for page in ("calendar", "pomodoro"):
        assert frame(page)[1].tobytes() == initial[page][1].tobytes()
    assert client.delete(url, headers=csrf).status_code == 204
    assert client.get(url, headers=bearer).json() == {"data": None}
    assert frame("todo")[1].tobytes() == original.tobytes()
    assert len(client.get(PATH + "/audit", params={"action": "replace"}).json()["data"]) == 2
    assert any(region["x"] == LEFT and region["action"] == "complete" for region in regions)



def test_upgrade_from_0003_preserves_entry_and_widget_order(tmp_path):
    database = Database(tmp_path / "previous.sqlite3")
    alembic = Config(str(BACKEND / "alembic.ini"))
    with database.engine.begin() as db:
        db.exec_driver_sql("BEGIN IMMEDIATE")
        alembic.attributes["connection"] = db
        command.upgrade(alembic, "0003")
        stamp = "2026-11-25T13:30:00.000000+00:00"
        db.exec_driver_sql(
            "INSERT INTO task (id,title,description,priority,completed,kindle_visible,created_at,updated_at,position)"
            " VALUES (41,'Legacy task','','normal',1,1,?,?,8)", (stamp, stamp),
        )
        db.exec_driver_sql(
            "INSERT INTO deadline (id,title,description,priority,completed,kindle_visible,created_at,updated_at,"
            "due_date,archived) VALUES (42,'Legacy deadline','','normal',0,1,?,?,'2026-12-05',1)", (stamp, stamp),
        )
        original = Preferences().model_dump(mode="json")
        original["widgets"].pop()
        original["widgets"].reverse()
        settings = json.dumps(original)
        db.exec_driver_sql("INSERT INTO dashboard_settings (id,preferences) VALUES (1,?)", (settings,))
    database.migrate()
    with database.engine.connect() as db:
        assert db.exec_driver_sql("SELECT id,completed,position,updated_at,source,external_ref FROM task").one() == (
            41, 1, 8, stamp, None, None,
        )
        assert db.exec_driver_sql("SELECT id,archived,created_at,source,external_ref FROM deadline").one() == (
            42, 1, stamp, None, None,
        )
        updated = json.loads(db.exec_driver_sql("SELECT preferences FROM dashboard_settings").scalar_one())
        assert updated["widgets"] == original["widgets"] + [{"key": "briefing", "visible": False, "limit": 1}]
        assert db.exec_driver_sql("PRAGMA integrity_check").scalar_one() == "ok"
    database.close()


def test_openapi_only_declares_bearer_for_scoped_routes(dashboard):
    _, client = dashboard
    contract = client.get("/openapi.json").json()
    assert contract["components"]["securitySchemes"]["AssistantBearer"]["scheme"] == "bearer"
    paths = contract["paths"]
    assert sum({"AssistantBearer": []} in op.get("security", []) for route in paths.values() for op in route.values()) == 12
    assert paths["/api/v1/tasks/{item_id}"]["put"]["responses"]["409"]["headers"].keys() == {"Link", "ETag"}
    for path, method in (("/api/v1/settings", "get"), ("/api/v1/briefing", "delete"), ("/api/v1/audit", "get")):
        assert {"AssistantBearer": []} not in paths[path][method].get("security", [])
