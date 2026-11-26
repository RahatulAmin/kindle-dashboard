from datetime import datetime
from pathlib import Path
from sys import path

ROOT = Path(__file__).resolve().parents[1]
path.insert(0, str(ROOT / "backend"))

from app.rendering.landscape import TaskRow, render_landscape
from app.rendering.muse import layout_briefing
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
        title="A Weekly release priorities and commitments for the project coordination meeting",
        lines=[
            "Coordinate the daily release review, confirm owners for open decisions, and update the shared notes.",
            "Review the supplier schedule and confirm that the revised delivery dates fit the project milestones.",
            "Prepare the workshop agenda, share the outline with reviewers, and confirm room access before lunch.",
            "Check the remaining accessibility findings and document the fixes that are ready for a further pass.",
            "Collect the budget updates from each pod and summarize the outstanding approvals before the meeting.",
            "Confirm the train reservation, share the departure time, and pack the materials for tomorrow's tour.",
        ],
        updated_at=updated,
    )
    assert len(maximum.title) == 80 and all(len(line) == 100 for line in maximum.lines)
    examples = [
        ("todo-briefing", "todo", briefing, 2), ("todo-empty", "todo", None, 2),
        ("todo-maximum", "todo", maximum, 2), ("calendar", "calendar", briefing, 1),
        ("pomodoro", "pomodoro", briefing, 1), ("muse", "muse", briefing, 1),
        ("muse-empty", "muse", None, 1),
    ]
    max_pages = layout_briefing(maximum, True).pages
    examples.extend((f"muse-maximum-{number}", "muse", maximum, number)
                    for number in range(1, len(max_pages) + 1))
    for name, page, value, number in examples:
        (output / f"{name}.png").write_bytes(render_landscape(
            page, now, "Montréal, Québec", weather, tasks if page == "todo" else None,
            page_number=number, page_count=3 if page == "todo" else 1,
            prayers=prayers, briefing=value, expanded=True,
        ))


if __name__ == "__main__":
    main()
