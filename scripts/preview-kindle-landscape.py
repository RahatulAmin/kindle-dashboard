from datetime import datetime
from pathlib import Path
from sys import path

ROOT = Path(__file__).resolve().parents[1]
path.insert(0, str(ROOT / "backend"))

from app.rendering.landscape import TaskRow, render_landscape
from app.services.dashboard import TORONTO
from app.services.weather import Weather


def main():
    output = ROOT / "docs/phase3a-previews"
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
    for name, page, rows, count in [
        ("todo", "todo", tasks, 2),
        ("calendar", "calendar", [], 1),
        ("pomodoro", "pomodoro", [], 1),
        ("todo-mixed", "todo", mixed, 1),
    ]:
        (output / f"{name}.png").write_bytes(
            render_landscape(page, now, "Montréal, Québec", weather, rows, page_count=count)
        )


if __name__ == "__main__":
    main()
