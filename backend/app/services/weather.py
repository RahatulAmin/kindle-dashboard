import json
import math
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from threading import Lock
from time import monotonic
from typing import Literal
from urllib.parse import urlencode
from urllib.request import urlopen

from app.core.logging import logger
from app.schemas.dashboard import WeatherLocation

CONDITIONS = {
    0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog", 51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    56: "Freezing drizzle", 57: "Freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Light showers", 81: "Rain showers", 82: "Heavy showers", 85: "Snow showers",
    86: "Heavy snow showers", 95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with hail",
}


@dataclass(frozen=True)
class Weather:
    status: Literal["fresh", "stale", "unavailable"]
    temperature: float | None = None
    condition: str | None = None
    high: float | None = None
    low: float | None = None
    updated_at: str | None = None


def fetch_weather(location: WeatherLocation) -> Weather:
    params = urlencode({
        "latitude": location.latitude, "longitude": location.longitude,
        "current": "temperature_2m,weather_code",
        "daily": "temperature_2m_max,temperature_2m_min",
        "temperature_unit": "celsius", "timezone": location.timezone, "forecast_days": 1,
    })
    with urlopen("https://api.open-meteo.com/v1/forecast?" + params, timeout=4) as response:
        payload = json.loads(response.read(65536))
    current, daily = payload["current"], payload["daily"]
    temperature = float(current["temperature_2m"])
    high, low = float(daily["temperature_2m_max"][0]), float(daily["temperature_2m_min"][0])
    if not all(math.isfinite(value) for value in (temperature, high, low)):
        raise ValueError("Non-finite weather temperature")
    return Weather("fresh", temperature, CONDITIONS.get(int(current["weather_code"]), "Unknown"),
                   high, low, datetime.now(UTC).isoformat())


class WeatherCache:
    def __init__(self):
        self.lock = Lock()
        self.entry: tuple[tuple, Weather, float, float] | None = None

    def get(self, location: WeatherLocation) -> Weather:
        key = (location.latitude, location.longitude, location.timezone)
        entry = self.entry
        now = monotonic()
        previous = Weather("unavailable")
        if entry and entry[0] == key:
            _, cached, fresh_until, retry_at = entry
            if now < fresh_until:
                return cached
            if cached.updated_at:
                previous = replace(cached, status="stale")
            if now < retry_at:
                return previous

        if not self.lock.acquire(blocking=False):
            return previous
        try:
            if self.entry is not entry:
                # A concurrent fetch completed between reading the entry and acquiring the lock.
                if self.entry and self.entry[0] == key:
                    return self.entry[1]
            try:
                current = fetch_weather(location)
            except (OSError, ValueError, KeyError, IndexError, TypeError, OverflowError) as exc:
                logger.warning("Weather update failed (%s)", type(exc).__name__)
                self.entry = (key, previous, 0, monotonic() + 60)
                return previous
            self.entry = (key, current, monotonic() + 900, 0)
            return current
        finally:
            self.lock.release()
