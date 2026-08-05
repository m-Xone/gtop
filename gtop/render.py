"""Curses renderer — paints a :data:`Frame` onto the terminal.

The renderer is pad-backed: content wider or taller than the visible window
lives in an off-screen :func:`curses.newpad` and the visible region is a
scrollable viewport onto it. This lets the view layer emit as many lines as
it likes without worrying about the terminal size.
"""

from __future__ import annotations

import contextlib
import curses
from collections.abc import Sequence

from .widgets import Color, Line, line_width

#: The full ordered collection of lines making up one rendered screen.
Frame = Sequence[Line]


# Map semantic colors → curses color-pair indices. Pair 0 is reserved for the
# terminal default, so non-default entries start at 1.
_COLOR_PAIRS: dict[Color, int] = {
    Color.RED: 1,
    Color.GREEN: 2,
    Color.YELLOW: 3,
    Color.BLUE: 4,
}

_CURSES_FG: dict[Color, int] = {
    Color.RED: curses.COLOR_RED,
    Color.GREEN: curses.COLOR_GREEN,
    Color.YELLOW: curses.COLOR_YELLOW,
    Color.BLUE: curses.COLOR_BLUE,
}

#: Horizontal scroll step, in columns, for the left/right keys.
HSCROLL_STEP = 4

#: Background that inherits the terminal's own color. ncurses supports this
#: after use_default_colors(); PDCurses (windows-curses) does not, so the
#: renderer falls back to an explicit black background.
_INHERIT_BACKGROUND = -1


class CursesRenderer:
    """Draws a :data:`Frame` into a curses window, with scrolling support."""

    def __init__(self, stdscr: curses.window) -> None:
        self._stdscr = stdscr
        self._pad: curses.window | None = None
        self._pad_size: tuple[int, int] = (0, 0)
        self._scroll_y = 0
        self._scroll_x = 0
        self._content_size: tuple[int, int] = (0, 0)

    # ---- lifecycle -------------------------------------------------------

    def setup(self) -> None:
        """Configure the curses window for rendering."""
        # Not every terminal supports hiding the cursor.
        with contextlib.suppress(curses.error):
            curses.curs_set(0)
        self._stdscr.keypad(True)
        self._init_colors()

    @staticmethod
    def _init_colors() -> None:
        """Register color pairs, degrading to monochrome if unavailable.

        Tries the terminal's own background first, then an explicit black.
        The second attempt is what makes color work under PDCurses, which
        windows-curses builds on and which rejects a -1 background.
        """
        if not curses.has_colors():
            return
        try:
            curses.start_color()
        except curses.error:
            return  # No color support at all; monochrome is fine.

        for background in (_INHERIT_BACKGROUND, curses.COLOR_BLACK):
            if background == _INHERIT_BACKGROUND:
                try:
                    curses.use_default_colors()
                except curses.error:
                    continue  # Terminal can't inherit; try explicit black.
            try:
                for color, pair in _COLOR_PAIRS.items():
                    curses.init_pair(pair, _CURSES_FG[color], background)
                return
            except curses.error:
                continue  # Fall through to the next background candidate.

    # ---- drawing ---------------------------------------------------------

    def draw(self, frame: Frame) -> None:
        """Render ``frame`` into the pad, then refresh the viewport."""
        rows = max(1, len(frame))
        cols = max(1, max((line_width(line) for line in frame), default=1))
        self._content_size = (rows, cols)
        self._ensure_pad(rows, cols)
        pad = self._pad
        assert pad is not None

        pad.erase()
        for y, line in enumerate(frame):
            x = 0
            for seg in line:
                if not seg.text:
                    continue
                # Writing to the last cell of a pad raises; truncation at
                # the content edge is the desired behavior here. Kept as a bare
                # try/except rather than contextlib.suppress: this runs once
                # per segment per frame.
                try:  # noqa: SIM105
                    pad.addstr(y, x, seg.text, self._attr(seg.color))
                except curses.error:
                    pass
                x += len(seg.text)

        self._blit()

    def draw_message(self, msg: str) -> None:
        """Clear the screen and display a single-line status message."""
        self._stdscr.erase()
        width = self._screen_size()[1]
        with contextlib.suppress(curses.error):
            self._stdscr.addnstr(0, 0, msg, max(1, width - 1))
        self._stdscr.refresh()

    # ---- scrolling -------------------------------------------------------

    def scroll(self, dy: int = 0, dx: int = 0) -> None:
        """Move the viewport by a relative offset."""
        self._scroll_y += dy
        self._scroll_x += dx
        self._clamp_scroll()

    def scroll_to(self, y: int = 0, x: int = 0) -> None:
        """Move the viewport to an absolute offset."""
        self._scroll_y = y
        self._scroll_x = x
        self._clamp_scroll()

    def scroll_to_bottom(self) -> None:
        """Move the viewport to the last page of content."""
        self._scroll_y = self._content_size[0]
        self._clamp_scroll()

    @property
    def scroll_offset(self) -> tuple[int, int]:
        """The current ``(y, x)`` viewport offset."""
        return self._scroll_y, self._scroll_x

    def page_size(self) -> int:
        """Number of lines to move for a page-up/page-down keypress."""
        return max(1, int(self._screen_size()[0] * 0.9))

    # ---- internals -------------------------------------------------------

    def _attr(self, color: Color) -> int:
        pair = _COLOR_PAIRS.get(color)
        if pair is None:
            return 0
        try:
            return curses.color_pair(pair)
        except curses.error:
            return 0  # Color pairs unavailable (monochrome terminal).

    def _screen_size(self) -> tuple[int, int]:
        height, width = self._stdscr.getmaxyx()
        return max(1, height), max(1, width)

    def _ensure_pad(self, content_rows: int, content_cols: int) -> None:
        height, width = self._screen_size()
        # The pad must cover the content and be at least as large as the
        # visible window, so a short frame still fills the screen.
        pad_rows = max(content_rows + 1, height)
        pad_cols = max(content_cols + 1, width)
        if self._pad is None or self._pad_size != (pad_rows, pad_cols):
            self._pad = curses.newpad(pad_rows, pad_cols)
            self._pad_size = (pad_rows, pad_cols)

    def _clamp_scroll(self) -> None:
        height, width = self._screen_size()
        rows, cols = self._content_size
        self._scroll_y = max(0, min(self._scroll_y, max(0, rows - height)))
        self._scroll_x = max(0, min(self._scroll_x, max(0, cols - width)))

    def _blit(self) -> None:
        height, width = self._screen_size()
        self._clamp_scroll()

        self._stdscr.erase()
        self._stdscr.noutrefresh()
        pad = self._pad
        if pad is None:
            return
        try:
            pad.noutrefresh(self._scroll_y, self._scroll_x, 0, 0, height - 1, width - 1)
            curses.doupdate()
        except curses.error:
            pass  # Window too small to blit into; skip this frame.
