"""Output-agnostic widget primitives.

Widgets produce a :class:`Line` — an immutable sequence of :class:`Segment`
objects, each tagged with a semantic :class:`Color`. A renderer (curses,
ANSI, plain text, …) is responsible for turning segments into actual
on-screen output. No ANSI, no curses, no I/O in this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Sequence, Tuple


class Color(Enum):
    """Semantic color names. The renderer maps them to concrete attributes."""

    DEFAULT = "default"
    RED = "red"
    GREEN = "green"
    YELLOW = "yellow"
    BLUE = "blue"


@dataclass(frozen=True)
class Segment:
    """A contiguous run of characters drawn with a single color."""

    text: str
    color: Color = Color.DEFAULT


# A Line is a sequence of segments with no trailing newline; the renderer
# handles vertical placement.
Line = Tuple[Segment, ...]


def plain(text: str) -> Segment:
    return Segment(text, Color.DEFAULT)


def colored(text: str, color: Color) -> Segment:
    return Segment(text, color)


def line_width(line: Line) -> int:
    """Return the rendered character width of *line*."""
    return sum(len(s.text) for s in line)


_RULE_CHAR = "\u2500"


def hrule(width: int = 96) -> Line:
    """Return a horizontal-rule line ``width`` characters wide."""
    return (plain(_RULE_CHAR * max(0, width)),)


def row(cells: Iterable[str], widths: Iterable[int]) -> Line:
    """Render a left-justified table row with two-space column gutters."""
    text = "".join(str(c).ljust(w) + "  " for c, w in zip(cells, widths))
    return (plain(text),)


def blank() -> Line:
    """An empty line (renders as a blank row)."""
    return (plain(""),)


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

    def _color_for(self, pct: float) -> Color:
        if pct > self.thresholds[1]:
            return Color.RED
        if pct > self.thresholds[0]:
            return Color.YELLOW
        return Color.GREEN

    def render(self) -> Line:
        pct = max(0.0, min(self.pct, 1.0))
        progress = int(pct * self.bar_length)
        # Reserve three cells in the middle for the numeric percentage.
        fill = min(self.bar_length - 3, progress)
        empty = max(0, self.bar_length - progress - 3)

        title = self.title[: self.title_w].ljust(self.title_w)
        epi = self.epilogue[:20]
        filled = self.fill_char[:1] * fill + f"{pct * 100:.0f}".ljust(3)

        return (
            plain(f"{title} {self.unit} ["),
            colored(filled, self._color_for(pct)),
            plain(self.empty_char * empty + f"] {epi}"),
        )
