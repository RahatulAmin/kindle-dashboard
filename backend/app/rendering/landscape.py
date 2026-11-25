from calendar import day_name, month_abbr
from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO
import unicodedata

from PIL import Image, ImageDraw

from app.rendering.dashboard import fit_line
from app.rendering.landscape_layout import (
    CLOCK_DIVIDER_Y, CLOCK_WIDTH, DATE_DIVIDER_Y, HEIGHT, LEFT, MAIN_CENTER, NAV_Y,
    PANEL_CENTER, PANEL_INSET, PANEL_TEXT_WIDTH, PANEL_X, PRAYER_Y, RIGHT,
    TABS, TAB_LABELS, TASK_TEXT_X, WEATHER_ICON_Y, WIDTH, Page, pagination_controls, row_box, tab_box,
)
from app.rendering.typography import font
from app.services.dashboard import TORONTO
from app.services.prayer_times import PRAYERS, PrayerDay
from app.services.weather import Weather

INK, SECONDARY, RULE = 0, 75, 195


@dataclass(frozen=True)
class TaskRow:
    title: str
    completed: bool = False
    priority: str = "normal"
    due_date: date | None = None


def date_clock(now: datetime) -> tuple[str, str, str, str, str]:
    local = now.astimezone(TORONTO)
    return (str(local.day), month_abbr[local.month].upper(), day_name[local.weekday()],
            f"{local.hour % 12 or 12}:{local.minute:02}", "AM" if local.hour < 12 else "PM")


def temperature(value: float) -> str:
    return str(round(value)).replace("-", "−") + "°"


def label(draw, xy, text, size, weight="Regular", fill=INK, anchor="ls"):
    draw.text(xy, text, font=font(size, weight), fill=fill, anchor=anchor)


def inline(draw, center, baseline, main, extra, size, extra_size):
    big, small = font(size, "Bold"), font(extra_size, "Medium")
    gap = 10
    width = draw.textlength(main, font=big) + gap + draw.textlength(extra, font=small)
    x = center - width / 2
    label(draw, (x, baseline), main, size, "Bold")
    label(draw, (x + draw.textlength(main, font=big) + gap, baseline), extra, extra_size, "Medium")


def icon(draw, name, cx, cy, ink=INK):
    if name == "todo":
        draw.rounded_rectangle((cx-13, cy-13, cx+13, cy+13), 3, outline=ink, width=2)
        draw.line((cx-7, cy, cx-2, cy+5, cx+8, cy-6), fill=ink, width=3, joint="curve")
    elif name == "calendar":
        draw.rounded_rectangle((cx-14, cy-11, cx+14, cy+13), 3, outline=ink, width=2)
        draw.line((cx-14, cy-3, cx+14, cy-3), fill=ink, width=2)
        for x in (cx-7, cx+7):
            draw.line((x, cy-15, x, cy-7), fill=ink, width=2)
    else:
        draw.ellipse((cx-12, cy-10, cx+12, cy+14), outline=ink, width=2)
        draw.line((cx-4, cy-15, cx+4, cy-15), fill=ink, width=2)
        draw.line((cx, cy-5, cx, cy+2, cx+5, cy+2), fill=ink, width=2)


def weather_icon(draw, condition: str | None, y: int):
    x = PANEL_CENTER
    name = (condition or "").lower()
    clear = "clear" in name
    partly = "partly" in name
    if not name or name == "unknown":
        draw.ellipse((x-26, y-26, x+26, y+26), outline=SECONDARY, width=3)
        draw.line((x-9, y, x+9, y), fill=SECONDARY, width=3)
        return
    if clear or partly:
        sx, sy = (x+15, y-11) if partly else (x, y)
        draw.ellipse((sx-15, sy-15, sx+15, sy+15), outline=INK, width=3)
        for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1), (0.71, 0.71),
                       (-0.71, 0.71), (0.71, -0.71), (-0.71, -0.71)):
            draw.line((sx+dx*21, sy+dy*21, sx+dx*28, sy+dy*28), fill=INK, width=3)
    if clear:
        return
    draw.rounded_rectangle((x-34, y-7, x+28, y+19), 13, fill=255, outline=INK, width=3)
    draw.ellipse((x-23, y-21, x+12, y+13), fill=255, outline=INK, width=3)
    draw.rectangle((x-20, y-4, x+9, y+14), fill=255)
    if "fog" in name:
        for offset in (27, 34):
            draw.line((x-24, y+offset, x+22, y+offset), fill=INK, width=2)
    elif "snow" in name:
        for dx in (-19, 0, 19):
            draw.ellipse((x+dx-2, y+26, x+dx+2, y+30), fill=INK)
    elif "thunder" in name:
        draw.polygon((x+3, y+18, x-7, y+33, x-1, y+33, x-3, y+40,
                      x+9, y+28, x+3, y+28), fill=INK)
    elif any(word in name for word in ("rain", "shower", "drizzle")):
        for dx in (-18, 0, 18):
            draw.line((x+dx, y+26, x+dx-5, y+34), fill=INK, width=2)


def device_indicators(draw, battery, wifi):
    if wifi:
        for radius in (5, 10, 15):
            draw.arc((949-radius, 32-radius, 949+radius, 32+radius), 224, 316, fill=INK, width=2)
        draw.ellipse((948, 31, 950, 33), fill=INK)
    if battery is not None:
        draw.rounded_rectangle((974, 17, 995, 30), 2, outline=INK)
        draw.rectangle((996, 21, 998, 26), fill=INK)
        fill = round(16 * battery / 100)
        if fill:
            draw.rectangle((977, 20, 976+fill, 27), fill=INK)


def clock_size(draw, time):
    size = 112
    while draw.textlength(time, font=font(size, "Bold")) > CLOCK_WIDTH:
        size -= 1
    return size


def information(draw, now, location, weather, compact=False):
    day, month, weekday, time, meridiem = date_clock(now)
    label(draw, (PANEL_CENTER, 145), time, clock_size(draw, time), "Bold", anchor="ms")
    label(draw, (PANEL_CENTER, 183), meridiem, 27, "Medium", anchor="ms")
    inline(draw, PANEL_CENTER, 309, day, month, 82, 35)
    label(draw, (PANEL_CENTER, 349), weekday, 27, "Medium", SECONDARY, "ms")
    for y in (CLOCK_DIVIDER_Y, DATE_DIVIDER_Y):
        draw.line((PANEL_X + PANEL_INSET, y, WIDTH - PANEL_INSET, y), fill=RULE)
    icon_y = 412 if compact else WEATHER_ICON_Y
    temperature_y, condition_y, range_y, stale_y, location_y = (
        (499, 525, 550, 573, 591) if compact else (508, 543, 578, 605, 640)
    )
    weather_icon(draw, weather.condition if weather.temperature is not None else None, icon_y)
    if weather.temperature is None:
        label(draw, (PANEL_CENTER, condition_y), "Weather unavailable", 24, "Medium", SECONDARY, "ms")
    else:
        label(draw, (PANEL_CENTER, temperature_y), temperature(weather.temperature) + "C", 58, "Bold", anchor="ms")
        condition = fit_line(draw, weather.condition or "Unknown", font(23), PANEL_TEXT_WIDTH)
        label(draw, (PANEL_CENTER, condition_y), condition, 23, anchor="ms")
        if weather.high is not None and weather.low is not None:
            label(draw, (PANEL_CENTER, range_y), f"H {temperature(weather.high)} / L {temperature(weather.low)}",
                  21, "Medium", SECONDARY, "ms")
        if weather.status == "stale":
            label(draw, (PANEL_CENTER, stale_y), "Last known weather", 16, fill=SECONDARY, anchor="ms")
    name = fit_line(draw, unicodedata.normalize("NFC", location), font(16), PANEL_TEXT_WIDTH)
    label(draw, (PANEL_CENTER, location_y), name, 16, fill=SECONDARY, anchor="ms")


def todo(draw, tasks, page_number, page_count, prayer_strip):
    for index, task in enumerate(tasks):
        box = row_box(index)
        cy = box.y + box.h // 2
        x = box.x + 22
        draw.rounded_rectangle((x-15, cy-15, x+15, cy+15), 4,
                               fill=INK if task.completed else 255, outline=INK, width=2)
        if task.completed:
            draw.line((x-8, cy, x-2, cy+6, x+8, cy-6), fill=255, width=3, joint="curve")
        details = []
        if task.priority != "normal":
            details.append(task.priority.capitalize() + " priority")
        if task.due_date:
            details.append(f"Due {month_abbr[task.due_date.month]} {task.due_date.day}")
        title = fit_line(draw, unicodedata.normalize("NFC", task.title), font(24, "Medium"), RIGHT - TASK_TEXT_X)
        y = cy if details else cy + 8
        label(draw, (TASK_TEXT_X, y), title, 24, "Medium", SECONDARY if task.completed else INK)
        if task.completed:
            draw.line((TASK_TEXT_X, y-8, TASK_TEXT_X+draw.textlength(title, font=font(24, "Medium")), y-8),
                      fill=SECONDARY, width=2)
        if details:
            label(draw, (TASK_TEXT_X, cy+24), "  ·  ".join(details), 16, fill=SECONDARY)
        draw.line((LEFT, box.y+box.h-1, RIGHT, box.y+box.h-1), fill=RULE)
    if not tasks:
        label(draw, (MAIN_CENTER, 344), "No tasks to display", 30, "Medium", anchor="ms")
    if page_count > 1:
        label(draw, (MAIN_CENTER, 626 - (NAV_Y - PRAYER_Y if prayer_strip else 0)), f"{page_number} of {page_count}", 18,
              "Medium", SECONDARY, "ms")
        for target, _, box, text in pagination_controls(page_number, page_count, prayer_strip):
            draw.rounded_rectangle(box.bounds, radius=8, outline=SECONDARY, width=1)
            center_x, center_y = box.x + box.w // 2, box.y + box.h // 2
            previous = target < page_number
            label(draw, (center_x + (10 if previous else -10), center_y + 8),
                  text, 22, "Bold", anchor="ms")
            arrow = center_x + (-59 if previous else 35)
            direction = -1 if previous else 1
            draw.polygon((arrow + 5 * direction, center_y, arrow - 4 * direction, center_y - 6,
                          arrow - 4 * direction, center_y + 6), fill=INK)


def draw_prayer_strip(draw, result: PrayerDay):
    draw.line((0, PRAYER_Y, WIDTH - 1, PRAYER_Y), fill=RULE)
    entries = list(zip(PRAYERS, result.today, strict=True))
    entries.insert(1, ("Sunrise", result.sunrise))
    for index, (name, timing) in enumerate(entries):
        left, right = index * WIDTH // len(entries), (index + 1) * WIDTH // len(entries)
        center = (left + right) // 2
        selected = name == result.current_name
        color = 255 if selected else INK
        if selected:
            draw.rectangle((left, PRAYER_Y, right - 1, NAV_Y - 1), fill=INK)
        elif index:
            draw.line((left, PRAYER_Y, left, NAV_Y - 1), fill=RULE)
        label(draw, (center, PRAYER_Y + 25), name, 16, "Medium", color, "ms")
        label(draw, (center, PRAYER_Y + 52), timing, 23, "Bold", color, "ms")
    draw.line((0, NAV_Y - 1, WIDTH - 1, NAV_Y - 1), fill=RULE)


def render_landscape(page: Page, now: datetime, location: str, weather: Weather,
                     tasks: list[TaskRow] | None = None, page_number: int = 1,
                     page_count: int = 1, *, battery: int | None = None, wifi: bool = False,
                     prayers: PrayerDay | None = None) -> bytes:
    image = Image.new("L", (WIDTH, HEIGHT), 255)
    draw = ImageDraw.Draw(image)
    draw.line((PANEL_X, 0, PANEL_X, PRAYER_Y if prayers is not None else NAV_Y), fill=RULE)
    draw.line((LEFT, 110, RIGHT, 110), fill=RULE)
    label(draw, (LEFT, 80), TAB_LABELS[page], 47, "Bold")
    if page == "todo":
        todo(draw, tasks or [], page_number, page_count, prayers is not None)
    elif page == "calendar":
        icon(draw, "calendar", MAIN_CENTER, 282)
        label(draw, (MAIN_CENTER, 354), "Calendar preview", 34, "Bold", anchor="ms")
        label(draw, (MAIN_CENTER, 398), "Monthly view and agenda coming in Phase 3B.", 20,
              fill=SECONDARY, anchor="ms")
    else:
        label(draw, (MAIN_CENTER, 196), "Focus session", 23, "Medium", SECONDARY, "ms")
        label(draw, (MAIN_CENTER, 332), "25:00", 112, "Bold", anchor="ms")
        draw.line((MAIN_CENTER-144, 371, MAIN_CENTER+144, 371), fill=RULE, width=4)
        draw.ellipse((MAIN_CENTER-148, 367, MAIN_CENTER-140, 375), fill=SECONDARY)
        for x, text in ((MAIN_CENTER-76, "Start"), (MAIN_CENTER+76, "Reset")):
            draw.rounded_rectangle((x-59, 426, x+59, 479), 4, outline=RULE)
            label(draw, (x, 461), text, 22, "Medium", SECONDARY, "ms")
        label(draw, (MAIN_CENTER, 530), "Preview · Timer controls disabled", 19, fill=SECONDARY, anchor="ms")
    information(draw, now, location, weather, compact=prayers is not None)
    device_indicators(draw, battery, wifi)
    if prayers is not None:
        draw_prayer_strip(draw, prayers)
    for index, tab in enumerate(TABS):
        box = tab_box(index)
        center = box.x + box.w // 2
        color = 255 if tab == page else INK
        if tab == page:
            draw.rectangle(box.bounds, fill=INK)
        elif index:
            draw.line((box.x, NAV_Y, box.x, HEIGHT-1), fill=RULE)
        icon(draw, tab, center, 695, color)
        label(draw, (center, 738), TAB_LABELS[tab], 22, "Medium", color, "ms")
    draw.line((0, NAV_Y, WIDTH-1, NAV_Y), fill=INK)
    output = BytesIO()
    image.save(output, "PNG", compress_level=3)
    return output.getvalue()
