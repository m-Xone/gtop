"""Terminal output primitives: colors, screen control, progress bars, tables.

Everything in this module is pure string formatting — no I/O, no data
gathering. Views compose these widgets to build frames.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Iterable, Sequence


class ANSI:
    """ANSI escape sequences used for colored output."""

    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"


_RULE_CHAR = "\u2500"  # box-drawing horizontal line


def clear_screen() -> None:
    """Home the cursor and clear to end of screen."""
    sys.stdout.write("\033[H\033[J")


def hrule(width: int = 96) -> str:
    """Return a horizontal rule of box-drawing characters."""
    return _RULE_CHAR * width


def row(cells: Iterable[str], widths: Iterable[int]) -> str:
    """Render a left-justified table row with two-space column gutters."""
    return "".join(str(c).ljust(w) + "  " for c, w in zip(cells, widths)) + "\n"


@dataclass(frozen=True)
class ProgressBar:
    """A colored ``[<fill><pct><empty>]`` bar with a title and optional suffix.

    ``pct`` is a 0..1 fraction; values outside that range are clamped.
    ``thresholds`` flip the fill color from green → yellow → red.
    """

    title: str
    pct: float
    bar_length: int = 60
    fill_char: str = "|"
    empty_char: str = " "
    title_w: int = 14
    unit: str = " "
    thresholds: Sequence[float] = (0.5, 0.9)
    epilogue: str = ""
    separator: str = "\n"

    def _color(self, pct: float) -> str:
        if pct > self.thresholds[1]:
            return ANSI.RED
        if pct > self.thresholds[0]:
            return ANSI.YELLOW
        return ANSI.GREEN

    def render(self) -> str:
        pct = max(0.0, min(self.pct, 1.0))
        progress = int(pct * self.bar_length)
        # Reserve 3 cells in the middle for the numeric percentage.
        fill = min(self.bar_length - 3, progress)
        empty = max(0, self.bar_length - progress - 3)

        bar = (
            "["
            + self._color(pct)
            + self.fill_char[:1] * fill
            + f"{pct * 100:.0f}".ljust(3)
            + ANSI.RESET
            + self.empty_char * empty
            + "]"
        )
        title = self.title[: self.title_w].ljust(self.title_w)
        epilogue = self.epilogue[:20]
        return f"{title} {self.unit} {bar} {epilogue}{self.separator}"
