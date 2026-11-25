from dataclasses import dataclass
from typing import Literal

Page = Literal["todo", "calendar", "pomodoro"]
WIDTH, HEIGHT = 1024, 758
PANEL_X, NAV_Y = 696, 666
LEFT, RIGHT = 42, 654
ROWS_Y, ROW_HEIGHT, PAGE_SIZE = 121, 81, 6
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


PREVIOUS = Box(LEFT, 612, 112, 47)
NEXT = Box(RIGHT - 112, 612, 112, 47)
