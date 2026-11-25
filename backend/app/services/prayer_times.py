from calendar import monthrange
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
import json
from threading import Lock
from time import monotonic
from typing import Annotated, Literal
from urllib.parse import urlencode
from urllib.request import urlopen

from pydantic import Field, StringConstraints, model_validator
from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert

from app.core.logging import logger
from app.models.dashboard import PrayerMonth, PrayerSettings
from app.schemas.dashboard import InputModel
from app.services.dashboard import TORONTO

PRAYERS = ("Fajr", "Dhuhr", "Asr", "Maghrib", "Isha")
METHODS = {
    0: "Jafari / Shia Ithna-Ashari", 1: "University of Islamic Sciences, Karachi",
    2: "Islamic Society of North America (ISNA)", 3: "Muslim World League",
    4: "Umm Al-Qura University, Makkah", 5: "Egyptian General Authority of Survey",
    7: "Institute of Geophysics, University of Tehran", 8: "Gulf Region",
    9: "Kuwait", 10: "Qatar", 11: "Singapore (MUIS)", 12: "France (UOIF)",
    13: "Türkiye (Diyanet)", 14: "Spiritual Administration of Muslims of Russia",
    15: "Moonsighting Committee Worldwide", 16: "Dubai", 17: "Malaysia (JAKIM)",
    18: "Tunisia", 19: "Algeria", 20: "Indonesia (KEMENAG)", 21: "Morocco",
    22: "Lisbon", 23: "Jordan",
}
RETRY_SECONDS = 900
Location = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=90)]
Offset = Annotated[int, Field(ge=-120, le=120)]


class Adjustments(InputModel):
    fajr: Offset = 0
    dhuhr: Offset = 0
    asr: Offset = 0
    maghrib: Offset = 0
    isha: Offset = 0


class PrayerPreferences(InputModel):
    enabled: bool = False
    city: Location = "Montréal"
    country: Location = "Canada"
    method: int = 2
    school: Literal[0, 1] | None = None
    latitude_adjustment: Literal[1, 2, 3] = 3
    adjustments: Adjustments = Field(default_factory=Adjustments)

    @model_validator(mode="after")
    def check_calculation(self):
        if self.method not in METHODS:
            raise ValueError("Choose a supported AlAdhan calculation method")
        if self.enabled and self.school is None:
            raise ValueError("Select Standard or Hanafi Asr before enabling the strip")
        return self

    def cache_key(self) -> str:
        calculation = self.model_dump_json(exclude={"enabled"})
        return sha256(calculation.encode()).hexdigest()


@dataclass(frozen=True)
class PrayerDay:
    today: tuple[str, ...] = ("--:--",) * len(PRAYERS)
    current_name: str | None = None
    updated_at: str | None = None


def prayer_preferences(db) -> PrayerPreferences:
    row = db.get(PrayerSettings, 1)
    return PrayerPreferences.model_validate(row.preferences) if row else PrayerPreferences()


def save_prayer_preferences(db, value: PrayerPreferences):
    statement = insert(PrayerSettings).values(id=1, preferences=value.model_dump())
    db.execute(statement.on_conflict_do_update(
        index_elements=[PrayerSettings.id], set_={"preferences": statement.excluded.preferences},
    ))
    db.commit()


def month_key(day: date) -> str:
    return day.strftime("%Y-%m")


def months_to_cache(now: datetime) -> tuple[str, str]:
    first = now.astimezone(TORONTO).date().replace(day=1)
    return month_key(first), month_key((first + timedelta(days=32)).replace(day=1))


def fetch_month(config: PrayerPreferences, month: str) -> dict:
    if config.school is None:
        raise ValueError("Asr calculation is required")
    adjustments = config.adjustments
    tune = (0, adjustments.fajr, 0, adjustments.dhuhr, adjustments.asr,
            adjustments.maghrib, 0, adjustments.isha, 0)
    params = urlencode({
        "city": config.city, "country": config.country, "method": config.method,
        "school": config.school, "latitudeAdjustmentMethod": config.latitude_adjustment,
        "timezonestring": TORONTO.key, "iso8601": "true", "shafaq": "general",
        "tune": ",".join(map(str, tune)),
    })
    year, number = map(int, month.split("-"))
    url = f"https://api.aladhan.com/v1/calendarByCity/{year}/{number}?{params}"
    with urlopen(url, timeout=5) as response:
        payload = json.loads(response.read(256 * 1024))
    if payload["code"] != 200:
        raise ValueError("AlAdhan did not return a schedule")
    days = {}
    for row in payload["data"]:
        day = datetime.strptime(row["date"]["gregorian"]["date"], "%d-%m-%Y").date()
        if month_key(day) != month or row["meta"]["timezone"] != TORONTO.key:
            raise ValueError("Wrong schedule month or timezone")
        instants = [datetime.fromisoformat(row["timings"][name]) for name in PRAYERS]
        if any(moment.utcoffset() is None or
               moment.astimezone(TORONTO).utcoffset() != moment.utcoffset() for moment in instants):
            raise ValueError("Invalid prayer time offset")
        days[day.isoformat()] = [moment.astimezone(UTC).isoformat() for moment in instants]
    if len(days) != monthrange(year, number)[1]:
        raise ValueError("Incomplete prayer month")
    return days


def time_label(moment: datetime) -> str:
    local = moment.astimezone(TORONTO)
    return f"{local.hour % 12 or 12}:{local.minute:02} {'AM' if local.hour < 12 else 'PM'}"


def prayer_day(db, config: PrayerPreferences, now: datetime, *, include_update=False) -> PrayerDay:
    current = now.astimezone(UTC)
    today = current.astimezone(TORONTO).date()
    key = config.cache_key()
    updated_at = None
    if include_update:
        updated_at = db.scalar(select(func.max(PrayerMonth.updated_at)).where(PrayerMonth.calculation == key))

    row = db.get(PrayerMonth, (key, month_key(today)))
    values = row.days.get(today.isoformat(), []) if row else []
    if not values:
        return PrayerDay(updated_at=updated_at)

    moments = tuple(map(datetime.fromisoformat, values))
    started = ((moment, name) for moment, name in zip(moments, PRAYERS, strict=True) if moment <= current)
    # Before Fajr, the active slot is still the previous day's Isha.
    _, current_name = max(started, key=lambda prayer: prayer[0], default=(None, "Isha"))
    return PrayerDay(tuple(map(time_label, moments)), current_name, updated_at=updated_at)


class PrayerCache:
    def __init__(self):
        self.lock = Lock()
        self.retry_after: dict[tuple[str, str], float] = {}

    def refresh(self, database, config: PrayerPreferences, now: datetime, *, force=False) -> bool:
        """Fill current and next months without holding the SQLite connection during HTTP."""
        if config.school is None:
            return False
        with self.lock if force else _try_lock(self.lock) as acquired:
            if not force and not acquired:
                return False
            success = True
            self.retry_after = {key: until for key, until in self.retry_after.items() if until > monotonic()}
            for month in months_to_cache(now):
                key = (config.cache_key(), month)
                with database.sessions() as db:
                    if not force and db.get(PrayerMonth, key):
                        continue
                if not force and key in self.retry_after:
                    success = False
                    continue
                try:
                    days = fetch_month(config, month)
                except (OSError, ValueError, KeyError, TypeError) as error:
                    logger.warning("Prayer schedule refresh failed (%s)", type(error).__name__)
                    self.retry_after[key] = monotonic() + RETRY_SECONDS
                    success = False
                    continue
                with database.sessions() as db:
                    statement = insert(PrayerMonth).values(
                        calculation=key[0], month=month, days=days, updated_at=datetime.now(UTC).isoformat(),
                    )
                    db.execute(statement.on_conflict_do_update(
                        index_elements=[PrayerMonth.calculation, PrayerMonth.month],
                        set_={"days": statement.excluded.days, "updated_at": statement.excluded.updated_at},
                    ))
                    db.commit()
                self.retry_after.pop(key, None)
            return success


@contextmanager
def _try_lock(lock):
    acquired = lock.acquire(blocking=False)
    try:
        yield acquired
    finally:
        if acquired:
            lock.release()
