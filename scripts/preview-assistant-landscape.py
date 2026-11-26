from datetime import datetime
from pathlib import Path
from sys import path

ROOT = Path(__file__).resolve().parents[1]
path.insert(0, str(ROOT / "backend"))

from app.rendering.landscape import TaskRow, render_landscape
from app.schemas.assistant import BriefingOutput
from app.services.dashboard import TORONTO
from app.services.prayer_times import PrayerDay
from app.services.weather import Weather


def main():
    output = ROOT / "docs/assistant-previews"
    output.mkdir(exist_ok=True)
    now = datetime(2026, 11, 25, 12, 30, tzinfo=TORONTO)
    updated = now.replace(minute=15).isoformat()
    weather = Weather("fresh", -0.1, "Partly cloudy", 1, -5)
    prayers = PrayerDay(("5:45 AM", "11:46 AM", "2:03 PM", "4:16 PM", "5:45 PM"), "Dhuhr", sunrise="7:07 AM")
    tasks = [TaskRow(title, completed=done) for title, done in (
        ("Review design notes", False), ("Confirm workshop time", True),
        ("Update the reference list", False), ("Prepare meeting agenda", False),
        ("Review this week’s notes", False),
    )]
    briefing = BriefingOutput(title="Muse Briefing", lines=[
        "Review the agenda before 2 PM.",
        "Workshop confirmation is due Friday.",
        "Tomorrow: Montréal train at 8:15 AM.",
    ], updated_at=updated)
    maximum = BriefingOutput(
        title="Long briefing title for layout review".ljust(80, "!"),
        lines=[(f"{index}. This long sample line demonstrates how the Kindle truncates a full-length briefing line.").ljust(100, "!")
               for index in range(1, 7)],
        updated_at=updated,
    )
    for name, page, value in (
        ("todo-briefing", "todo", briefing), ("todo-empty", "todo", None),
        ("todo-maximum", "todo", maximum), ("calendar", "calendar", None), ("pomodoro", "pomodoro", None),
    ):
        (output / f"{name}.png").write_bytes(render_landscape(
            page, now, "Montréal, Québec", weather, tasks if page == "todo" else None,
            page_number=2 if page == "todo" else 1, page_count=3 if page == "todo" else 1,
            prayers=prayers, briefing=value,
        ))


if __name__ == "__main__":
    main()
