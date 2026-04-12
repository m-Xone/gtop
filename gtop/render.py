"""Curses renderer — paints a :data:`Frame` onto the terminal.

The renderer is pad-backed: content wider or taller than the visible window
lives in an off-screen :func:`curses.newpad` and the visible region is a
scrollable viewport onto it. This lets the view layer emit as many lines as
it likes without worrying about the terminal size.
"""
from __future__ import annotations

import curses
from typing import List, Optional, Sequence, Tuple

from .widgets import Color, Line, Segment, line_width

# A Frame is the full ordered collection of lines making up one "screen".
Frame = Sequence[Line]


# Map semantic colors → curses color-pair indices. Pair 0 is reserved for
# the terminal default, so non-default entries start at 1.
_COLOR_PAIRS: dict = {
    Color.RED: 1,
    Color.GREEN: 2,
    Color.YELLOW: 3,
    Color.BLUE: 4,
}

_CURSES_FG: dict = {
    Color.RED: curses.COLOR_RED,
    Color.GREEN: curses.COLOR_GREEN,
    Color.YELLOW: curses.COLOR_YELLOW,
    Color.BLUE: curses.COLOR_BLUE,
}


class CursesRenderer:
    """Draws a :data:`Frame` into a curses window, with scrolling support."""

    def __init__(self, stdscr) -> None:
        self._stdscr = stdscr
        self._pad = None
        self._pad_size: Tuple[int, int] = (0, 0)
        self._scroll_y = 0
        self._scroll_x = 0

    # ---- lifecycle -------------------------------------------------------

    def setup(self) -> None:
        """Configure the curses window for rendering."""
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        self._stdscr.keypad(True)
        if curses.has_colors():
            try:
                curses.start_color()
                curses.use_default_colors()
                for color, pair in _COLOR_PAIRS.items():
                    curses.init_pair(pair, _CURSES_FG[color], -1)
            except curses.error:
                pass  # Degrade gracefully on color-less terminals.

    # ---- drawing ---------------------------------------------------------

    def draw(self, frame: Frame) -> None:
        """Render ``frame`` into the pad, then refresh the viewport."""
        content_rows = max(1, len(frame))
        content_cols = max(
            1, max((line_width(line) for line in frame), default=1)
        )
        self._ensure_pad(content_rows, content_cols)
        assert self._pad is not None

        self._pad.erase()
        for y, line in enumerate(frame):
            x = 0
            for seg in line:
                if not seg.text:
                    continue
                try:
                    self._pad.addstr(y, x, seg.text, self._attr(seg.color))
                except curses.error:
                    # Writes beyond the pad raise; truncation is fine here.
                    pass
                x += len(seg.text)

        self._blit(content_rows, content_cols)

    def draw_message(self, msg: str) -> None:
        """Clear the screen and display a single-line status message."""
        self._stdscr.erase()
        try:
            self._stdscr.addnstr(0, 0, msg, self._screen_width() - 1)
        except curses.error:
            pass
        self._stdscr.refresh()

    # ---- scrolling -------------------------------------------------------

    def scroll(self, dy: int = 0, dx: int = 0) -> None:
        self._scroll_y += dy
        self._scroll_x += dx

    def scroll_to(self, y: int = 0, x: int = 0) -> None:
        self._scroll_y = y
        self._scroll_x = x

    # ---- internals -------------------------------------------------------

    def _attr(self, color: Color) -> int:
        if color is Color.DEFAULT:
            return 0
        pair = _COLOR_PAIRS.get(color)
        if pair is None:
            return 0
        try:
            return curses.color_pair(pair)
        except curses.error:
            return 0

    def _screen_size(self) -> Tuple[int, int]:
        height, width = self._stdscr.getmaxyx()
        return max(1, height), max(1, width)

    def _screen_width(self) -> int:
        return self._screen_size()[1]

    def _ensure_pad(self, content_rows: int, content_cols: int) -> None:
        height, width = self._screen_size()
        # Pad must be at least as large as the visible window, plus enough
        # room for the full content so we can scroll.
        pad_rows = max(content_rows + 1, height)
        pad_cols = max(content_cols + 1, width)
        if self._pad is None or self._pad_size != (pad_rows, pad_cols):
            self._pad = curses.newpad(pad_rows, pad_cols)
            self._pad_size = (pad_rows, pad_cols)

    def _blit(self, content_rows: int, content_cols: int) -> None:
        height, width = self._screen_size()
        # Clamp scroll offsets to valid range.
        self._scroll_y = max(0, min(self._scroll_y, max(0, content_rows - height)))
        self._scroll_x = max(0, min(self._scroll_x, max(0, content_cols - width)))

        self._stdscr.erase()
        self._stdscr.noutrefresh()
        try:
            assert self._pad is not None
            self._pad.noutrefresh(
                self._scroll_y,
                self._scroll_x,
                0,
                0,
                height - 1,
                width - 1,
            )
            curses.doupdate()
        except curses.error:
            pass
