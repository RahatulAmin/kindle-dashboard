import base64
from datetime import UTC, date, datetime
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from sqlalchemy import select

from app.api import kindle_landscape
from app.core.config import ROOT, Settings
from app.main import create_app
from app.models.dashboard import Task
from app.rendering.dashboard import fit_line
from app.rendering.landscape import clock_size, date_clock, render_landscape, temperature
from app.rendering.landscape_layout import (
    CLOCK_DIVIDER_Y, CLOCK_WIDTH, DATE_DIVIDER_Y, NAV_Y, NEXT, PAGE_SIZE, PANEL_CENTER,
    PANEL_X, PREVIOUS, RIGHT, TASK_TEXT_X, WIDTH, pagination_controls, row_box, tab_box,
)
from app.rendering.typography import font
from app.schemas.dashboard import Preferences
from app.services.dashboard import save_preferences
from app.services.weather import Weather
from app.setup_admin import create_admin

HEADERS = {"access-token": "test-landscape-device"}
BASE = "/api/kindle/landscape"
FRAME = BASE + "/frame"
NOW = datetime(2026, 11, 25, 17, 30, tzinfo=UTC)
UNAVAILABLE = Weather("unavailable")


@pytest.fixture
def dashboard(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, database_path=tmp_path / "landscape.sqlite3",
                        trmnl_access_token=HEADERS["access-token"])
    app = create_app(settings)
    monkeypatch.setattr(app.state.weather, "get",
                        lambda location: Weather("fresh", -0.4, "Partly cloudy", 1, -5))
    with TestClient(app, base_url="https://testserver") as client:
        with app.state.database.sessions() as db:
            save_preferences(db, Preferences(kindle_data_enabled=True))
            db.add_all([
                Task(title=f"Task {i}", position=10 - i, completed=i == 2,
                     priority="high" if i == 3 else "normal", due_date=date(2026, 11, 26),
                     description="", kindle_visible=i != 0)
                for i in range(9)
            ])
            db.commit()
        yield client


def image(data):
    with Image.open(BytesIO(data)) as png:
        assert png.format == "PNG"
        png.load()
        return png.copy()


def frame(client, page="todo", number=1):
    response = client.get(FRAME, params={"page": page, "number": number}, headers=HEADERS)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def tasks(frame):
    return [region for region in frame["regions"] if region["action"] == "complete"]


def write(client, region, **override):
    payload = {"completed": region["completed"], "capability": region["capability"]}
    return client.put(f"{BASE}/tasks/{override.pop('task_id', region['task_id'])}/completion",
                      json={**payload, **override}, headers=HEADERS)


@pytest.mark.parametrize(("utc", "expected"), [
    (NOW, ("25", "NOV", "Wednesday", "12:30", "PM")),
    (datetime(2026, 11, 25, 5, tzinfo=UTC), ("25", "NOV", "Wednesday", "12:00", "AM")),
    (datetime(2026, 7, 1, 16, tzinfo=UTC), ("1", "JUL", "Wednesday", "12:00", "PM")),
    (datetime(2026, 7, 1, 5, 7, tzinfo=UTC), ("1", "JUL", "Wednesday", "1:07", "AM")),
    (datetime(2026, 11, 1, 5, 30, tzinfo=UTC), ("1", "NOV", "Sunday", "1:30", "AM")),
    (datetime(2026, 11, 1, 6, 30, tzinfo=UTC), ("1", "NOV", "Sunday", "1:30", "AM")),
])
def test_toronto_date_and_clock(utc, expected):
    assert date_clock(utc) == expected


def test_unicode_long_titles_negative_zero_and_empty_weather():
    draw = ImageDraw.Draw(Image.new("L", (600, 90)))
    for weight in ("Regular", "Medium", "Bold"):
        face = font(24, weight)
        assert bytes(face.getmask("é")) != bytes(face.getmask("e"))
        assert face.getname()[1] == weight
    title = fit_line(draw, "Montréal Québec " * 28, font(24, "Medium"), RIGHT - TASK_TEXT_X)
    assert title.startswith("Montréal Québec") and title.endswith("…")
    assert draw.textlength(title, font=font(24, "Medium")) <= RIGHT - TASK_TEXT_X
    assert temperature(-0.1) == temperature(-0.0) == "0°"
    assert temperature(-5) == "−5°"
    empty = image(render_landscape("todo", NOW, "Montréal, Québec", UNAVAILABLE))
    fresh = image(render_landscape("todo", NOW, "Montréal, Québec", Weather("fresh", 1, "Snow", 2, -5)))
    stale = image(render_landscape("todo", NOW, "Montréal, Québec", Weather("stale", 1, "Snow", 2, -5)))
    assert empty.mode == "L" and empty.size == (1024, 758)
    assert empty.crop((180, 318, 520, 350)).getextrema()[0] == 0
    assert empty.crop((720, 325, 1000, 615)).tobytes() != fresh.crop((720, 325, 1000, 615)).tobytes()
    assert fresh.crop((720, 585, 1000, 612)).tobytes() != stale.crop((720, 585, 1000, 612)).tobytes()


def test_frame_png_navigation_pagination_and_completed_style(dashboard):
    first = frame(dashboard)
    assert first["refresh_rate"] == 30
    assert first["filename"] != frame(dashboard)["filename"]
    assert len(tasks(first)) == PAGE_SIZE
    assert [task["task_id"] for task in tasks(first)] == [9, 8, 7, 6, 5, 4]
    for region, expected in zip(tasks(first), map(row_box, range(PAGE_SIZE)), strict=True):
        assert (region["x"], region["y"], region["w"], region["h"]) == (expected.x, expected.y, expected.w, expected.h)
    second = frame(dashboard, number=999)
    assert second["number"] == 2
    assert [task["task_id"] for task in tasks(second)] == [3, 2]
    png = image(base64.b64decode(second["png"]))
    assert png.getpixel((54, row_box(0).y + 35)) == 0
    assert png.getpixel((54, row_box(1).y + 35)) == 255
    for index, page in enumerate(("todo", "calendar", "pomodoro")):
        current = frame(dashboard, page)
        assert current["page"] == page
        if page != "todo":
            assert len(current["regions"]) == 3
        png = image(base64.b64decode(current["png"]))
        assert png.mode == "L" and png.size == (1024, 758)
        for tab in range(3):
            box = tab_box(tab)
            assert png.getpixel((box.x + 25, box.y + 18)) == (0 if tab == index else 255)


def test_complete_reverse_duplicates_stale_and_admin_visibility(dashboard):
    task = tasks(frame(dashboard))[0]
    assert write(dashboard, task).status_code == 204
    assert write(dashboard, task).status_code == 204
    assert dashboard.get("/api/v1/tasks", headers=HEADERS).status_code == 401
    reversal = tasks(frame(dashboard))[0]
    assert reversal["completed"] is False
    assert write(dashboard, reversal).status_code == 204
    assert write(dashboard, task).status_code == 409
    assert write(dashboard, reversal, task_id=8).status_code == 409
    with dashboard.app.state.database.sessions() as db:
        row = db.get(Task, 9)
        assert not row.completed
        row.title = "Edited through the shared task model"
        db.commit()
    stale = tasks(frame(dashboard))[0]
    with dashboard.app.state.database.sessions() as db:
        row = db.get(Task, 9)
        row.title = "Another edit"
        db.commit()
    assert write(dashboard, stale).status_code == 409
    with dashboard.app.state.database.sessions() as db:
        db.get(Task, 9).kindle_visible = False
        db.commit()
    assert write(dashboard, stale).status_code == 404
    assert all(row["task_id"] != 9 for row in tasks(frame(dashboard)))


def test_expired_tampered_and_invalid_requests(dashboard, monkeypatch):
    task = tasks(frame(dashboard))[0]
    assert write(dashboard, task, capability=task["capability"] + "a").status_code == 409
    assert write(dashboard, task, completed="true").status_code == 422
    assert write(dashboard, task, title="replace me").status_code == 422
    now = kindle_landscape.time()
    monkeypatch.setattr(kindle_landscape, "time", lambda: now + 91)
    assert write(dashboard, task).status_code == 409
    assert dashboard.get(FRAME, params={"page": "invalid"}, headers=HEADERS).status_code == 422
    assert dashboard.get(FRAME).status_code == 401
    assert dashboard.get(FRAME, headers={"access-token": "wrong"}).status_code == 401
    assert dashboard.put(f"{BASE}/tasks/9/completion", json={}).status_code == 401


def test_privacy_controls_empty_and_portrait_compatibility(dashboard):
    before = dashboard.get("/api/display", headers=HEADERS).json()
    assert set(before) == {"filename", "image_url", "refresh_rate"}
    assert before["refresh_rate"] == 30
    assert before["image_url"].endswith("/api/kindle/dashboard.png")
    assert image(dashboard.get(before["image_url"]).content).size == (758, 1024)
    task = tasks(frame(dashboard))[0]
    with dashboard.app.state.database.sessions() as db:
        for row in db.scalars(select(Task)):
            row.kindle_visible = False
        db.commit()
    assert len(frame(dashboard)["regions"]) == 3
    with dashboard.app.state.database.sessions() as db:
        save_preferences(db, Preferences())
    assert dashboard.get(FRAME, headers=HEADERS).status_code == 404
    assert write(dashboard, task).status_code == 404


def test_package_contents_exclude_settings_and_credentials():
    plugin = ROOT / "kindle-koreader"
    with ZipFile(plugin / "trmnl-landscape-muse.zip") as archive:
        assert archive.testzip() is None
        assert {Path(name).name for name in archive.namelist()} == {
            "main.lua", "_meta.lua", "landscape.lua", "LICENSE",
        }
        assert archive.read("trmnl.koplugin/landscape.lua") == (plugin / "landscape.lua").read_bytes()
        assert b'landscape.lua").attach(TrmnlDisplay)' in archive.read("trmnl.koplugin/main.lua")


def test_lua_interaction_harness(tmp_path, monkeypatch):
    import ctypes
    from ctypes.util import find_library
    import shutil
    import subprocess

    monkeypatch.chdir(ROOT)
    script = ROOT / "kindle-koreader/tests/landscape_spec.lua"
    with ZipFile(ROOT / "kindle-koreader/trmnl-landscape-muse.zip") as archive:
        archive.extract("trmnl.koplugin/main.lua", tmp_path)
    packaged = tmp_path / "trmnl.koplugin/main.lua"
    runner = tmp_path / "test.lua"
    runner.write_text(f"assert(loadfile({str(packaged)!r}))\ndofile({str(script)!r})\n")
    command = next(filter(None, map(shutil.which, ("luajit", "lua5.4", "lua"))), None)
    if command:
        subprocess.run([command, str(runner)], check=True)
        return
    library = find_library("lua5.4")
    if not library:
        pytest.skip("Install LuaJIT, Lua 5.4, or liblua5.4 to run the KOReader mock harness")
    lua = ctypes.CDLL(library)
    lua.luaL_newstate.restype = ctypes.c_void_p
    pointer = ctypes.c_void_p
    lua.luaL_openlibs.argtypes = [pointer]
    lua.luaL_loadfilex.argtypes = [pointer, ctypes.c_char_p, ctypes.c_char_p]
    lua.lua_pcallk.argtypes = [pointer, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_longlong, pointer]
    lua.lua_tolstring.argtypes = [pointer, ctypes.c_int, pointer]
    lua.lua_tolstring.restype = ctypes.c_char_p
    lua.lua_close.argtypes = [pointer]
    state = lua.luaL_newstate()
    assert state
    try:
        lua.luaL_openlibs(state)
        assert lua.luaL_loadfilex(state, bytes(runner), None) == 0, lua.lua_tolstring(state, -1, None)
        assert lua.lua_pcallk(state, 0, 0, 0, 0, None) == 0, lua.lua_tolstring(state, -1, None)
    finally:
        lua.lua_close(state)


def test_indicators_only_when_device_supplies_readings(dashboard):
    base = image(base64.b64decode(frame(dashboard)["png"]))
    region = (930, 12, 1005, 38)
    assert base.crop(region).getextrema() == (255, 255)
    response = dashboard.get(FRAME, headers={
        **HEADERS, "percent-charged": "71", "dashboard-wifi": "connected",
    })
    assert response.status_code == 200
    observed = image(base64.b64decode(response.json()["png"]))
    assert observed.crop(region).getextrema() == (0, 255)


def test_checked_task_syncs_with_the_admin_api(dashboard):
    account = {"username": "landscape-admin", "password": "a test-only administrator password"}
    create_admin(dashboard.app.state.database, **account)
    login = dashboard.post("/api/v1/auth/login", json=account, headers={"X-Kindle-Admin": "1"})
    assert login.status_code == 200
    task = tasks(frame(dashboard))[0]
    assert write(dashboard, task).status_code == 204
    admin_tasks = dashboard.get("/api/v1/tasks")
    assert admin_tasks.status_code == 200
    row = next(item for item in admin_tasks.json()["data"] if item["id"] == task["task_id"])
    assert row["completed"]
    payload = {key: value for key, value in row.items() if key not in {"id", "created_at", "updated_at"}}
    payload["completed"] = False
    csrf = {"X-CSRF-Token": login.json()["data"]["csrf_token"]}
    assert dashboard.put(f"/api/v1/tasks/{row['id']}", json=payload, headers=csrf).status_code == 200
    assert tasks(frame(dashboard))[0]["completed"] is True


def test_clock_first_panel_fits_and_matches_across_pages():
    draw = ImageDraw.Draw(Image.new("L", (WIDTH, NAV_Y)))
    assert 0.37 < (WIDTH - PANEL_X) / WIDTH < 0.39
    sizes = {time: clock_size(draw, time) for time in ("9:59", "12:00")}
    assert 100 <= sizes["12:00"] < sizes["9:59"] <= 112
    for time, size in sizes.items():
        bounds = draw.textbbox((PANEL_CENTER, 145), time, font=font(size, "Bold"), anchor="ms")
        assert bounds[0] >= PANEL_CENTER - CLOCK_WIDTH // 2
        assert bounds[2] <= PANEL_CENTER + CLOCK_WIDTH // 2
        assert bounds[1] > 38 and bounds[3] < CLOCK_DIVIDER_Y
    panels = [
        image(render_landscape(page, NOW, "Montréal", UNAVAILABLE)).crop((PANEL_X, 0, WIDTH, NAV_Y))
        for page in ("todo", "calendar", "pomodoro")
    ]
    assert panels[0].tobytes() == panels[1].tobytes() == panels[2].tobytes()
    for y in (CLOCK_DIVIDER_Y, DATE_DIVIDER_Y):
        assert panels[0].getpixel((PANEL_CENTER - PANEL_X, y)) == 195


def test_pagination_targets_fit_reduced_main_area(dashboard):
    for current, box, target in ((1, NEXT, 2), (2, PREVIOUS, 1)):
        value = frame(dashboard, number=current)
        controls = [region for region in value["regions"] if region["y"] < NAV_Y
                    and region["action"] == "navigate"]
        assert len(controls) == 1
        control = controls[0]
        assert (control["x"], control["y"], control["w"], control["h"]) == (box.x, box.y, box.w, box.h)
        assert control["number"] == target
        assert box.x + box.w <= RIGHT and box.y + box.h < NAV_Y
        assert value["number"] == frame(dashboard, number=current)["number"]


def test_pagination_footer_has_clearance_and_tap_padding():
    controls = list(pagination_controls(2, 3))
    assert [target for target, _, _, _ in controls] == [1, 3]
    preview = image(render_landscape("todo", NOW, "Montréal", UNAVAILABLE, page_number=2, page_count=3))
    for _, hit, visible, _ in controls:
        assert hit.w >= 180 and hit.h >= 76
        assert hit.y > row_box(PAGE_SIZE - 1).bounds[3]
        assert hit.bounds[3] < NAV_Y
        assert visible.x - hit.x == visible.y - hit.y == 12
        assert hit.bounds[2] - visible.bounds[2] == hit.bounds[3] - visible.bounds[3] == 12
        center = visible.x + visible.w // 2
        assert preview.getpixel((center, visible.y)) == 75
        assert preview.getpixel((center, visible.y + 1)) == 255
        assert preview.getpixel((center, hit.y)) == 255
    assert controls[1][1].x - controls[0][1].bounds[2] > 150
