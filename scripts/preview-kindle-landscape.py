import argparse
from datetime import datetime
from pathlib import Path
from sys import path

ROOT = Path(__file__).resolve().parents[1]
path.insert(0, str(ROOT / "backend"))

from app.rendering.landscape import TaskRow, render_landscape
from app.rendering.landscape_layout import task_page_size
from app.services.dashboard import TORONTO
from app.services.prayer_times import PrayerDay
from app.services.weather import Weather


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prayer-times", action="store_true")
    options = parser.parse_args()
    output = ROOT / ("docs/prayer-times-previews" if options.prayer_times else "docs/phase3a-previews")
    output.mkdir(exist_ok=True)
    now = datetime(2026, 11, 25, 12, 30, tzinfo=TORONTO)
    weather = Weather("fresh", -0.1, "Partly cloudy", 1, -5)
    tasks = [
        TaskRow("Review design notes", priority="high", due_date=now.date()),
        TaskRow("Book the Montréal train", due_date=now.date().replace(day=27)),
        TaskRow("Outline next week’s priorities"),
        TaskRow("Reply to Québec workshop invitation", priority="low"),
        TaskRow("Organize reference files"),
        TaskRow("Review the week’s notes"),
    ]
    mixed = [tasks[0], TaskRow(tasks[1].title, completed=True), tasks[2],
             TaskRow(tasks[3].title, completed=True, priority="low"), *tasks[4:]]
    examples = [
        ("todo", "todo", tasks, 1, 2),
        ("calendar", "calendar", [], 1, 1),
        ("pomodoro", "pomodoro", [], 1, 1),
    ]
    prayers = None
    if options.prayer_times:
        prayers = PrayerDay(("5:45 AM", "11:46 AM", "2:03 PM", "4:16 PM", "5:45 PM"), "Dhuhr", sunrise="7:04 AM")
        examples[0] = ("todo", "todo", tasks[:task_page_size(True)], 2, 3)
    else:
        examples.append(("todo-mixed", "todo", mixed, 2, 3))
    for name, page, rows, number, count in examples:
        (output / f"{name}.png").write_bytes(render_landscape(
            page, now, "Montréal, Québec", weather, rows, page_number=number, page_count=count, prayers=prayers,
        ))


if __name__ == "__main__":
    main()
