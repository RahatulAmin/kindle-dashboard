from dataclasses import dataclass

from PIL import ImageDraw, ImageFont

from app.models.dashboard import Deadline, Task
from app.rendering.kindle import RenderContext, render_png
from app.schemas.dashboard import Preferences
from app.services.dashboard import TORONTO, days_until
from app.services.weather import Weather


@dataclass(frozen=True)
class Section:
    title: str
    lines: list[str]


def fit_line(draw, value, font, width):
    line = " ".join(value.split())
    if draw.textlength(line, font=font) <= width:
        return line
    while line and draw.textlength(line + "…", font=font) > width:
        line = line[:-1]
    return line.rstrip() + "…"


def countdown(days: int) -> str:
    if days == 0:
        return "Today"
    if days < 0:
        return f"{-days}d overdue"
    return f"In {days}d"


def render_dashboard(settings, preferences: Preferences, tasks: list[Task],
                     deadlines: list[Deadline], weather: Weather) -> bytes:
    def draw_dashboard(draw: ImageDraw.ImageDraw, context: RenderContext):
        weather_lines = ["Weather unavailable"]
        if weather.temperature is not None:
            stale = " (stale)" if weather.status == "stale" else ""
            weather_lines = [
                f"{weather.temperature:.0f} °C • {weather.condition}{stale}",
                f"High {weather.high:.0f} °C  Low {weather.low:.0f} °C · Open-Meteo",
            ]
        sections = {
            "datetime": Section("Date and time", [context.now.strftime("%a %b %d, %Y  %H:%M %Z")]),
            "weather": Section(preferences.weather.name, weather_lines),
            "tasks": Section("Tasks", [item.title for item in tasks] or ["No open tasks"]),
            "deadlines": Section("Deadlines", [
                f"{countdown(days_until(item.due_date, context.now.astimezone(TORONTO).date()))} • {item.title}" for item in deadlines
            ] or ["No active deadlines"]),
        }
        ordered = []
        for widget in preferences.widgets:
            if widget.visible and widget.key in sections:
                section = sections[widget.key]
                lines = section.lines[:widget.limit] if widget.key in {"tasks", "deadlines"} else section.lines
                ordered.append(Section(section.title, lines))

        margin = context.scale // 20
        row = context.scale // 19
        body = ImageFont.load_default(size=context.scale // 29)
        heading = ImageFont.load_default(size=context.scale // 24)
        title = ImageFont.load_default(size=context.scale // 17)
        width = context.width - 2 * margin
        draw.text((margin, margin), fit_line(draw, preferences.dashboard_title, title, width), font=title, fill=0)
        y = margin + row * 2

        # Reserve each section heading and allocate remaining rows in rounds.
        available = max(0, (context.height - margin - y) // row - len(ordered))
        counts = [0] * len(ordered)
        for line_index in range(max((len(section.lines) for section in ordered), default=0)):
            for index, section in enumerate(ordered):
                if available and line_index < len(section.lines):
                    counts[index] += 1
                    available -= 1

        for section, count in zip(ordered, counts, strict=True):
            if y + row > context.height - margin:
                break
            draw.text((margin, y), fit_line(draw, section.title, heading, width), font=heading, fill=0)
            y += row
            for line in section.lines[:count]:
                draw.text((margin, y), fit_line(draw, line, body, width), font=body, fill=0)
                y += row

    return render_png(settings, widgets=(draw_dashboard,))
