import base64
from calendar import monthrange
from contextlib import closing
from dataclasses import asdict
from datetime import UTC, date, datetime
from io import BytesIO
from itertools import combinations
import json
import sqlite3
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings
from app.db.database import Database
from app.main import create_app
from app.models.dashboard import PrayerMonth, Task
from app.rendering.landscape import render_landscape
from app.rendering.landscape_layout import HEIGHT, NAV_Y, PRAYER_Y, WIDTH, tab_box, task_page_size
from app.schemas.dashboard import Preferences
from app.services import prayer_times as prayers
from app.services.dashboard import TORONTO, save_preferences
from app.services.weather import Weather
from app.setup_admin import create_admin


def month_fixtures(month, fajr_hour=6):
    year, month_number = map(int, month.split("-"))
    for day in range(1, monthrange(year, month_number)[1] + 1):
        local = datetime(year, month_number, day, tzinfo=TORONTO)
        yield local, [
            local.replace(hour=hour, minute=day).isoformat() for hour in (fajr_hour, 12, 15, 17, 19)
        ]


def schedules(month, fajr_hour=6):
    return {
        local.date().isoformat(): [datetime.fromisoformat(value).astimezone(UTC).isoformat() for value in times]
        for local, times in month_fixtures(month, fajr_hour)
    }


def test_aladhan_month_timezone_and_calculation_parameters(monkeypatch):
    seen = []
    def respond(url, timeout):
        seen.append(url)
        assert timeout == 5
        rows = [{
            "date": {"gregorian": {"date": local.strftime("%d-%m-%Y")}},
            "meta": {"timezone": TORONTO.key},
            "timings": dict(zip(prayers.PRAYERS, values, strict=True)),
        } for local, values in month_fixtures("2026-03")]
        return BytesIO(json.dumps({"code": 200, "data": rows}).encode())

    monkeypatch.setattr(prayers, "urlopen", respond)
    settings = prayers.PrayerPreferences(city="Montréal", country="Canada", school=1, method=3,
                                         latitude_adjustment=2, adjustments={"asr": 10, "isha": -5})
    result = prayers.fetch_month(settings, "2026-03")
    endpoint = urlsplit(seen[0])
    assert endpoint.path == "/v1/calendarByCity/2026/3"
    assert parse_qs(endpoint.query) == {
        "city": ["Montréal"], "country": ["Canada"], "school": ["1"], "method": ["3"],
        "latitudeAdjustmentMethod": ["2"], "timezonestring": ["America/Toronto"],
        "iso8601": ["true"], "shafaq": ["general"], "tune": ["0,0,0,0,10,0,0,-5,0"],
    }
    assert result["2026-03-07"][0].startswith("2026-03-07T11:07")
    assert result["2026-03-08"][0].startswith("2026-03-08T10:08")
    assert prayers.time_label(datetime.fromisoformat(result["2026-03-08"][0])) == "6:08 AM"


def test_midnight_next_prayer_and_month_boundary(tmp_path, monkeypatch):
    db = Database(tmp_path / "prayers.sqlite3")
    db.migrate()
    config = prayers.PrayerPreferences(enabled=True, school=0)
    midnight_eve = datetime(2026, 11, 30, 23, 59, tzinfo=TORONTO)
    monkeypatch.setattr(prayers, "fetch_month", lambda _, month: schedules(month))
    assert prayers.PrayerCache().refresh(db, config, midnight_eve)
    with db.sessions() as session:
        before = prayers.prayer_day(session, config, midnight_eve)
        assert before.today[0] == "6:30 AM"
        assert before.next_name == "Fajr" and before.tomorrow and before.next_time == "6:01 AM"
        midnight = datetime(2026, 12, 1, tzinfo=TORONTO)
        after = prayers.prayer_day(session, config, midnight)
        assert after.next_name == "Fajr" and not after.tomorrow and after.today[0] == "6:01 AM"
        exact = prayers.prayer_day(session, config, midnight.replace(hour=6, minute=1))
        assert exact.next_name == "Fajr"
        assert prayers.prayer_day(session, config, midnight.replace(hour=6, minute=2)).next_name == "Dhuhr"
        session.delete(session.get(PrayerMonth, (config.cache_key(), "2026-12")))
        session.commit()
        missing = prayers.prayer_day(session, config, midnight_eve)
        assert missing.tomorrow and missing.next_time is None
        assert prayers.prayer_day(session, config, midnight).today == ("--:--",) * 5
    db.close()


def test_fall_dst_offline_restart_and_setting_changes(tmp_path, monkeypatch):
    path = tmp_path / "prayers.sqlite3"
    db = Database(path)
    db.migrate()
    calls = []
    def fetch(config, month):
        calls.append((config.cache_key(), month))
        return schedules(month, fajr_hour=6 + config.school)
    monkeypatch.setattr(prayers, "fetch_month", fetch)
    initial = prayers.PrayerPreferences(enabled=True, school=0)
    now = datetime(2026, 11, 1, 10, 30, tzinfo=UTC)
    cache = prayers.PrayerCache()
    assert cache.refresh(db, initial, now)
    assert cache.refresh(db, initial, now)
    assert len(calls) == 2
    with db.sessions() as session:
        prayers.save_prayer_preferences(session, initial)
    db.close()
    reopened = Database(path)
    attempts = []
    def offline(*args):
        attempts.append(args)
        raise OSError("offline")
    monkeypatch.setattr(prayers, "fetch_month", offline)
    cache = prayers.PrayerCache()
    assert cache.refresh(reopened, initial, now)
    assert not cache.refresh(reopened, initial, now, force=True)
    assert len(attempts) == 2
    with reopened.sessions() as session:
        assert prayers.prayer_preferences(session) == initial
        result = prayers.prayer_day(session, initial, now, include_update=True)
        assert result.today[0] == "6:01 AM" and result.next_name == "Fajr" and result.updated_at
    alternates = initial.model_copy(update={"school": 1})
    assert not cache.refresh(reopened, alternates, now)
    assert not cache.refresh(reopened, alternates, now)
    assert len(attempts) == 4
    with reopened.sessions() as session:
        assert prayers.prayer_day(session, alternates, now).today == ("--:--",) * 5
    monkeypatch.setattr(prayers, "fetch_month", fetch)
    assert cache.refresh(reopened, alternates, now, force=True)
    with reopened.sessions() as session:
        assert prayers.prayer_day(session, alternates, now).today[0] == "7:01 AM"
        assert prayers.prayer_day(session, initial, now).today[0] == "6:01 AM"
    reopened.close()


def test_admin_frame_geometry_and_device_actions(tmp_path, monkeypatch):
    path = tmp_path / "prayers.sqlite3"
    settings = Settings(_env_file=None, database_path=path, trmnl_access_token="fixture")
    monkeypatch.setattr(prayers, "fetch_month", lambda _, month: schedules(month))
    app = create_app(settings)
    app.state.weather.get = lambda _: Weather("unavailable")
    with TestClient(app, base_url="https://testserver") as client:
        create_admin(app.state.database, "prayer-admin", "a temporary password")
        with app.state.database.sessions() as db:
            save_preferences(db, Preferences(kindle_data_enabled=True))
            db.add_all([Task(title=f"Task {n}", position=n, completed=False, priority="normal",
                             description="", kindle_visible=True) for n in range(12)])
            db.commit()
        device = {"access-token": "fixture"}
        location = "/api/v1/prayer-times"
        assert client.get(location, headers=device).status_code == 401
        auth = client.post("/api/v1/auth/login", json={"username": "prayer-admin", "password": "a temporary password"},
                           headers={"X-Kindle-Admin": "1"}).json()["data"]
        csrf = {"X-CSRF-Token": auth["csrf_token"]}
        defaults = client.get(location).json()["data"]["preferences"]
        assert defaults["method"] == 2 and defaults["school"] is None and not defaults["enabled"]
        assert client.put(location, headers=csrf, json={**defaults, "enabled": True}).status_code == 422
        assert client.put(location, json=defaults).status_code == 403
        url = "/api/kindle/landscape/frame"
        plain = client.get(url, headers=device).json()
        assert sum(region["action"] == "complete" for region in plain["regions"]) == task_page_size(False) == 6
        enabled = {**defaults, "enabled": True, "school": 1}
        assert client.put(location, headers=csrf, json=enabled).status_code == 200
        assert client.post(location + "/refresh", headers=csrf).status_code == 200
        view = client.get(location).json()["data"]
        assert view["last_updated_at"] and view["today"]["Fajr"] != "--:--"
        values = client.get(url + "?number=2", headers=device).json()
        action_regions = [region for region in values["regions"] if region["action"] == "complete"]
        assert len(action_regions) == task_page_size(True) == 5
        assert len(values["regions"]) <= 11
        page_controls = [region for region in values["regions"] if region["action"] == "navigate" and region["y"] < NAV_Y]
        assert {region["number"] for region in page_controls} == {1, 3}
        assert all(region["w"] == 184 and region["h"] == 78 for region in page_controls)
        for region in action_regions + page_controls:
            assert region["y"] + region["h"] < PRAYER_Y
        regions = values["regions"]
        for region in regions:
            assert 0 <= region["x"] < region["x"] + region["w"] <= WIDTH
            assert 0 <= region["y"] < region["y"] + region["h"] <= HEIGHT
        for first, second in combinations(regions, 2):
            assert (
                first["x"] + first["w"] <= second["x"]
                or second["x"] + second["w"] <= first["x"]
                or first["y"] + first["h"] <= second["y"]
                or second["y"] + second["h"] <= first["y"]
            )
        task = action_regions[0]
        result = client.put(f"/api/kindle/landscape/tasks/{task['task_id']}/completion", headers=device,
                            json={key: task[key] for key in ("completed", "capability")})
        assert result.status_code == 204
        assert client.get(url + "?number=2", headers=device).json()["number"] == 2
        for page in ("todo", "calendar", "pomodoro"):
            frame = client.get(url + f"?page={page}", headers=device).json()
            assert frame["refresh_rate"] == 30
            for index, tab in enumerate(("todo", "calendar", "pomodoro")):
                assert frame["regions"][index] == {
                    **asdict(tab_box(index)), "action": "navigate", "page": tab, "number": 1,
                }
            for region in frame["regions"][3:]:
                assert region["y"] + region["h"] <= PRAYER_Y
            with Image.open(BytesIO(base64.b64decode(frame["png"]))) as png:
                assert png.size == (1024, 758) and png.mode == "L"
        assert client.put(location, headers=csrf, json={**enabled, "enabled": False}).status_code == 200
        plain_again = client.get(url, headers=device).json()
        assert sum(region["action"] == "complete" for region in plain_again["regions"]) == 6
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT count(*) FROM task WHERE completed").fetchone() == (1,)


def test_same_noninteractive_strip_and_highlight_on_all_pages():
    now = datetime(2026, 11, 25, 12, 30, tzinfo=TORONTO)
    salat = prayers.PrayerDay(("6:00 AM", "12:00 PM", "3:00 PM", "5:00 PM", "7:00 PM"), "Asr")
    def strip(page, values):
        with Image.open(BytesIO(render_landscape(page, now, "Montréal", Weather("unavailable"), prayers=values))) as png:
            return png.crop((0, PRAYER_Y, WIDTH, NAV_Y))
    strips = [strip(page, salat) for page in ("todo", "calendar", "pomodoro")]
    assert strips[0].tobytes() == strips[1].tobytes() == strips[2].tobytes()
    assert [strips[0].getpixel((index * WIDTH // 5 + 10, 12)) for index in range(5)] == [255, 255, 0, 255, 255]
    tomorrow = strip("todo", prayers.PrayerDay(salat.today, "Fajr", True, "6:05 AM"))
    assert tomorrow.getpixel((10, 12)) == 0
    assert tomorrow.tobytes() != strip("todo", prayers.PrayerDay(salat.today, "Fajr")).tobytes()
    offline = strip("todo", prayers.PrayerDay())
    assert all(offline.getpixel((index * WIDTH // 5 + 10, 12)) == 255 for index in range(5))
