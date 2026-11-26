from calendar import month_abbr
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
import unicodedata

from PIL import Image

from app.rendering.landscape_layout import NAV_Y, PRAYER_Y, WIDTH
from app.rendering.typography import font
from app.schemas.assistant import BriefingOutput
from app.services.dashboard import TORONTO

CONTENT_X = 64
PRIORITY_X = CONTENT_X + 39
PRIORITY_SIZE = 30
TITLE_SIZE = 42
TITLE_Y = 126
TITLE_STEP = 48
ROW_STEP = 42
PRIORITY_GAP = 15


@lru_cache(maxsize=2)
def symbol_mask(size: int) -> Image.Image | None:
    asset = Path(__file__).with_name("muse-symbol.png")
    if not asset.is_file():
        return None
    with Image.open(asset) as source:
        mask = source.convert("RGBA").getchannel("A")
        mask.thumbnail((size, size), Image.Resampling.LANCZOS)
        return mask


def draw_symbol(image: Image.Image, x: int, y: int, size: int, ink: int) -> bool:
    mask = symbol_mask(size)
    if mask is None:
        return False
    x += (size - mask.width) // 2
    y += (size - mask.height) // 2
    image.paste(ink, (x, y, x + mask.width, y + mask.height), mask)
    return True


def wrap_text(text: str, size: int, width: int, weight: str = "Regular") -> tuple[str, ...]:
    measure = font(size, weight).getlength
    words = unicodedata.normalize("NFC", text).split()
    rows = []
    line = ""
    for word in words:
        proposal = f"{line} {word}" if line else word
        if measure(proposal) <= width:
            line = proposal
            continue
        if line:
            rows.append(line)
        line = ""
        # A single long URL or unbroken word can span several rows.
        for character in word:
            if line and measure(line + character) > width:
                rows.append(line)
                line = ""
            line += character
    if line:
        rows.append(line)
    return tuple(rows)


@dataclass(frozen=True)
class PriorityRow:
    text: str
    baseline: int
    starts_priority: bool


@dataclass(frozen=True)
class MuseLayout:
    title: tuple[str, ...]
    updated: str
    updated_y: int
    pages: tuple[tuple[PriorityRow, ...], ...]


def layout_briefing(briefing: BriefingOutput | None, prayer_strip: bool) -> MuseLayout:
    if briefing is None:
        return MuseLayout((), "", 0, ((),))

    title = wrap_text(briefing.title, TITLE_SIZE, WIDTH - 2 * CONTENT_X, "Bold")
    updated_y = TITLE_Y + (len(title) - 1) * TITLE_STEP + 31
    local = datetime.fromisoformat(briefing.updated_at).astimezone(TORONTO)
    time = f"{local.hour % 12 or 12}:{local.minute:02} {'AM' if local.hour < 12 else 'PM'}"
    updated = f"Updated {month_abbr[local.month]} {local.day}, {local.year} · {time}"

    start = updated_y + 56
    last = (PRAYER_Y if prayer_strip else NAV_Y) - 96
    baseline = start
    pages: list[list[PriorityRow]] = [[]]
    for priority in briefing.lines:
        lines = wrap_text(priority, PRIORITY_SIZE, WIDTH - PRIORITY_X - CONTENT_X)
        for index, line in enumerate(lines):
            if baseline > last and pages[-1]:
                pages.append([])
                baseline = start
            pages[-1].append(PriorityRow(line, baseline, index == 0))
            baseline += ROW_STEP
        baseline += PRIORITY_GAP
    return MuseLayout(title, updated, updated_y, tuple(tuple(page) for page in pages))
