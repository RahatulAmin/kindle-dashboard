from dataclasses import dataclass
from typing import Literal

Page = Literal["todo", "calendar", "pomodoro"]
WIDTH, HEIGHT = 1024, 758
PANEL_X, NAV_Y = 635, 666
LEFT, RIGHT = 42, PANEL_X - 42
MAIN_CENTER = (LEFT + RIGHT) // 2
TASK_TEXT_X = LEFT + 76
PANEL_CENTER = (PANEL_X + WIDTH) // 2
PANEL_INSET = 36
PANEL_TEXT_WIDTH = WIDTH - PANEL_X - 2 * PANEL_INSET
CLOCK_WIDTH = PANEL_TEXT_WIDTH - 40
CLOCK_DIVIDER_Y, DATE_DIVIDER_Y = 208, 368
WEATHER_ICON_Y = 418
ROWS_Y, ROW_HEIGHT, PAGE_SIZE = 121, 75, 6
TABS: tuple[Page, ...] = ("todo", "calendar", "pomodoro")
TAB_LABELS = {"todo": "Todo", "calendar": "Calendar", "pomodoro": "Pomodoro"}


@dataclass(frozen=True)
class Box:
    x: int
    y: int
    w: int
    h: int

    @property
    def bounds(self):
        return self.x, self.y, self.x + self.w - 1, self.y + self.h - 1


def tab_box(index: int) -> Box:
    start, stop = index * WIDTH // 3, (index + 1) * WIDTH // 3
    return Box(start, NAV_Y, stop - start, HEIGHT - NAV_Y)


def row_box(index: int) -> Box:
    return Box(LEFT, ROWS_Y + index * ROW_HEIGHT, 67, ROW_HEIGHT)


PREVIOUS = Box(LEFT, 580, 184, 78)
NEXT = Box(RIGHT - 184, 580, 184, 78)


def pagination_controls(number: int, count: int):
    for target, hit, text in ((number - 1, PREVIOUS, "Previous"), (number + 1, NEXT, "Next")):
        if 1 <= target <= count:
            visible = Box(hit.x + 12, hit.y + 12, hit.w - 24, hit.h - 24)
            yield target, hit, visible, text
