"""CursesRenderer: segment placement, color mapping, and scroll clamping."""

from __future__ import annotations

import curses
import sys

import pytest

from gtop.render import _COLOR_PAIRS, CursesRenderer
from gtop.widgets import Color, colored, plain


@pytest.fixture
def renderer(fake_curses, make_screen):
    screen = make_screen(height=10, width=40)
    r = CursesRenderer(screen)
    r.setup()
    return r, screen, fake_curses


class TestSetup:
    def test_enables_keypad_for_arrow_keys(self, renderer):
        _, screen, _ = renderer
        assert screen.keypad_enabled is True

    def test_survives_a_terminal_without_color(
        self, fake_curses, make_screen, monkeypatch
    ):
        monkeypatch.setattr(curses, "has_colors", lambda: False)
        CursesRenderer(make_screen()).setup()  # must not raise

    def test_survives_color_init_failure(self, fake_curses, make_screen, monkeypatch):
        def _boom():
            raise curses.error("no colors here")

        monkeypatch.setattr(curses, "start_color", _boom)
        CursesRenderer(make_screen()).setup()  # must not raise

    def test_survives_a_terminal_that_cannot_hide_the_cursor(
        self, fake_curses, make_screen, monkeypatch
    ):
        def _boom(n):
            raise curses.error("curs_set unsupported")

        monkeypatch.setattr(curses, "curs_set", _boom)
        CursesRenderer(make_screen()).setup()  # must not raise


class TestColorSetup:
    """Color negotiation, including the PDCurses/windows-curses fallback."""

    @pytest.fixture
    def pairs(self, fake_curses, monkeypatch):
        """Record every successful init_pair(pair, fg, bg) call."""
        recorded: list[tuple[int, int, int]] = []
        monkeypatch.setattr(
            curses,
            "init_pair",
            lambda pair, fg, bg: recorded.append((pair, fg, bg)),
        )
        return recorded

    def test_prefers_the_inherited_terminal_background(self, pairs, make_screen):
        CursesRenderer(make_screen()).setup()
        assert len(pairs) == len(_COLOR_PAIRS)
        assert {bg for _, _, bg in pairs} == {-1}

    def test_falls_back_to_black_when_the_terminal_cannot_inherit(
        self, pairs, make_screen, monkeypatch
    ):
        """PDCurses has no use_default_colors; color must survive anyway."""

        def _boom():
            raise curses.error("use_default_colors unsupported")

        monkeypatch.setattr(curses, "use_default_colors", _boom)
        CursesRenderer(make_screen()).setup()
        assert len(pairs) == len(_COLOR_PAIRS)
        assert {bg for _, _, bg in pairs} == {curses.COLOR_BLACK}

    def test_falls_back_to_black_when_a_minus_one_background_is_rejected(
        self, fake_curses, make_screen, monkeypatch
    ):
        """PDCurses accepts use_default_colors but rejects -1 in init_pair."""
        recorded: list[tuple[int, int, int]] = []

        def _init_pair(pair, fg, bg):
            if bg == -1:
                raise curses.error("bad background")
            recorded.append((pair, fg, bg))

        monkeypatch.setattr(curses, "init_pair", _init_pair)
        CursesRenderer(make_screen()).setup()
        assert len(recorded) == len(_COLOR_PAIRS)
        assert {bg for _, _, bg in recorded} == {curses.COLOR_BLACK}

    def test_every_semantic_color_gets_a_pair(self, pairs, make_screen):
        CursesRenderer(make_screen()).setup()
        assert {p for p, _, _ in pairs} == set(_COLOR_PAIRS.values())

    def test_no_pairs_are_registered_without_color_support(
        self, pairs, make_screen, monkeypatch
    ):
        monkeypatch.setattr(curses, "has_colors", lambda: False)
        CursesRenderer(make_screen()).setup()
        assert pairs == []

    def test_no_pairs_are_registered_when_start_color_fails(
        self, pairs, make_screen, monkeypatch
    ):
        def _boom():
            raise curses.error("start_color failed")

        monkeypatch.setattr(curses, "start_color", _boom)
        CursesRenderer(make_screen()).setup()
        assert pairs == []

    def test_monochrome_setup_still_renders(
        self, fake_curses, make_screen, monkeypatch
    ):
        monkeypatch.setattr(curses, "has_colors", lambda: False)
        r = CursesRenderer(make_screen())
        r.setup()
        r.draw([(colored("x", Color.RED),)])  # must not raise


class TestDraw:
    def test_places_each_line_on_its_own_row(self, renderer):
        r, _, pads = renderer
        r.draw([(plain("one"),), (plain("two"),), (plain("three"),)])
        rows = [w[0] for w in pads[-1].writes]
        assert rows == [0, 1, 2]

    def test_segments_advance_the_column_cursor(self, renderer):
        r, _, pads = renderer
        r.draw([(plain("abc"), plain("de"), plain("f"))])
        assert [(w[1], w[2]) for w in pads[-1].writes] == [
            (0, "abc"),
            (3, "de"),
            (5, "f"),
        ]

    def test_empty_segments_are_skipped(self, renderer):
        r, _, pads = renderer
        r.draw([(plain(""), plain("x"))])
        assert [w[2] for w in pads[-1].writes] == ["x"]

    def test_default_color_uses_no_attribute(self, renderer):
        r, _, pads = renderer
        r.draw([(plain("x"),)])
        assert pads[-1].writes[0][3] == 0

    @pytest.mark.parametrize(
        "color", [Color.RED, Color.GREEN, Color.YELLOW, Color.BLUE]
    )
    def test_semantic_colors_map_to_their_pair(self, renderer, color):
        r, _, pads = renderer
        r.draw([(colored("x", color),)])
        # The fake color_pair is `n << 8`.
        assert pads[-1].writes[0][3] == _COLOR_PAIRS[color] << 8

    def test_erases_before_repainting(self, renderer):
        r, _, pads = renderer
        r.draw([(plain("first"),)])
        r.draw([(plain("second"),)])
        assert pads[-1].erase_count == 2
        assert [w[2] for w in pads[-1].writes] == ["second"]

    def test_a_write_past_the_pad_edge_does_not_propagate(self, renderer, monkeypatch):
        r, _, pads = renderer
        r.draw([(plain("x"),)])

        def _boom(*a, **kw):
            raise curses.error("addstr out of bounds")

        monkeypatch.setattr(pads[-1], "addstr", _boom)
        r.draw([(plain("y"),)])  # must not raise

    def test_unencodable_text_is_redrawn_as_ascii(self, renderer, monkeypatch):
        """curses encodes with the locale's encoding; cp1252 has no U+2588."""
        r, _, pads = renderer
        r.draw([(plain("x"),)])
        pad = pads[-1]
        real_addstr = pad.addstr

        def _codepage_limited(y, x, text, attr=0):
            text.encode("cp1252")  # raises UnicodeEncodeError for █ and ─
            real_addstr(y, x, text, attr)

        monkeypatch.setattr(pad, "addstr", _codepage_limited)
        r.draw([(plain("███ ─── ok"),)])
        assert [w[2] for w in pad.writes] == ["### --- ok"]

    def test_unencodable_text_falls_back_to_question_marks(self, renderer, monkeypatch):
        """Glyphs with no ASCII stand-in still render rather than vanishing."""
        r, _, pads = renderer
        r.draw([(plain("x"),)])
        pad = pads[-1]
        real_addstr = pad.addstr

        def _ascii_only(y, x, text, attr=0):
            text.encode("ascii")
            real_addstr(y, x, text, attr)

        monkeypatch.setattr(pad, "addstr", _ascii_only)
        r.draw([(plain("café"),)])
        assert [w[2] for w in pad.writes] == ["caf?"]

    def test_a_second_encoding_failure_does_not_propagate(self, renderer, monkeypatch):
        r, _, pads = renderer
        r.draw([(plain("x"),)])

        def _always_fails(y, x, text, attr=0):
            raise UnicodeEncodeError("ascii", text, 0, 1, "nope")

        monkeypatch.setattr(pads[-1], "addstr", _always_fails)
        r.draw([(plain("█"),)])  # must not raise

    def test_pad_is_large_enough_for_the_content(self, renderer):
        r, _, pads = renderer
        r.draw([(plain("x" * 200),)] * 50)
        assert pads[-1].rows > 50
        assert pads[-1].cols > 200

    def test_pad_covers_the_window_even_for_a_tiny_frame(self, renderer):
        r, screen, pads = renderer
        r.draw([(plain("x"),)])
        assert pads[-1].rows >= screen.height
        assert pads[-1].cols >= screen.width

    def test_pad_is_reused_when_the_size_is_unchanged(self, renderer):
        r, _, pads = renderer
        r.draw([(plain("a"),)])
        r.draw([(plain("b"),)])
        assert len(pads) == 1

    def test_pad_is_rebuilt_when_content_grows(self, renderer):
        r, _, pads = renderer
        r.draw([(plain("a"),)])
        r.draw([(plain("x" * 500),)] * 100)
        assert len(pads) == 2

    def test_pad_is_rebuilt_when_the_terminal_resizes(self, renderer):
        r, screen, pads = renderer
        r.draw([(plain("a"),)])
        screen.height, screen.width = 50, 200
        r.draw([(plain("a"),)])
        assert len(pads) == 2

    def test_empty_frame_does_not_crash(self, renderer):
        r, _, _ = renderer
        r.draw([])


class TestScrolling:
    def _long_frame(self, n=100):
        return [(plain(f"line {i}"),) for i in range(n)]

    def test_starts_at_the_origin(self, renderer):
        r, _, _ = renderer
        r.draw(self._long_frame())
        assert r.scroll_offset == (0, 0)

    def test_relative_vertical_scroll(self, renderer):
        r, _, _ = renderer
        r.draw(self._long_frame())
        r.scroll(dy=5)
        assert r.scroll_offset[0] == 5

    def test_cannot_scroll_above_the_top(self, renderer):
        r, _, _ = renderer
        r.draw(self._long_frame())
        r.scroll(dy=-50)
        assert r.scroll_offset[0] == 0

    def test_cannot_scroll_past_the_last_page(self, renderer):
        r, screen, _ = renderer
        r.draw(self._long_frame(100))
        r.scroll(dy=10_000)
        assert r.scroll_offset[0] == 100 - screen.height

    def test_scroll_to_bottom_lands_on_the_last_page(self, renderer):
        r, screen, _ = renderer
        r.draw(self._long_frame(100))
        r.scroll_to_bottom()
        assert r.scroll_offset[0] == 100 - screen.height

    def test_content_shorter_than_the_window_cannot_scroll(self, renderer):
        r, _, _ = renderer
        r.draw(self._long_frame(3))
        r.scroll(dy=10)
        assert r.scroll_offset[0] == 0

    def test_horizontal_scroll_is_clamped_to_content_width(self, renderer):
        r, screen, _ = renderer
        r.draw([(plain("x" * 100),)])
        r.scroll(dx=10_000)
        assert r.scroll_offset[1] == 100 - screen.width

    def test_no_horizontal_scroll_for_narrow_content(self, renderer):
        r, _, _ = renderer
        r.draw([(plain("short"),)])
        r.scroll(dx=50)
        assert r.scroll_offset[1] == 0

    def test_scroll_to_sets_an_absolute_offset(self, renderer):
        r, _, _ = renderer
        r.draw([(plain("x" * 100),) for _ in range(100)])
        r.scroll(dy=40)
        r.scroll_to(2, 3)
        assert r.scroll_offset == (2, 3)

    def test_viewport_offset_is_passed_to_the_pad(self, renderer):
        r, _, pads = renderer
        frame = self._long_frame(100)
        r.draw(frame)
        r.scroll(dy=7)
        r.draw(frame)
        top, left = pads[-1].viewports[-1][0], pads[-1].viewports[-1][1]
        assert (top, left) == (7, 0)

    def test_viewport_is_bounded_by_the_window(self, renderer):
        r, screen, pads = renderer
        r.draw(self._long_frame())
        _, _, _, _, bottom, right = pads[-1].viewports[-1]
        assert (bottom, right) == (screen.height - 1, screen.width - 1)

    def test_page_size_is_just_under_a_full_screen(self, renderer):
        r, screen, _ = renderer
        assert 0 < r.page_size() < screen.height

    def test_page_size_is_at_least_one_line(self, fake_curses, make_screen):
        r = CursesRenderer(make_screen(height=1, width=10))
        assert r.page_size() >= 1


class TestDrawMessage:
    def test_writes_the_message(self, renderer):
        r, screen, _ = renderer
        r.draw_message("something went wrong")
        assert screen.messages == ["something went wrong"]

    def test_message_is_truncated_to_the_window(self, renderer):
        r, screen, _ = renderer
        r.draw_message("y" * 500)
        assert len(screen.messages[0]) == screen.width - 1

    def test_clears_the_screen_first(self, renderer):
        r, screen, _ = renderer
        before = screen.erase_count
        r.draw_message("hi")
        assert screen.erase_count > before


class TestDegenerateWindows:
    def test_zero_sized_window_is_treated_as_one_cell(self, fake_curses, make_screen):
        r = CursesRenderer(make_screen(height=0, width=0))
        r.draw([(plain("x"),)])  # must not raise or divide by zero

    def test_blit_failure_is_swallowed(self, renderer, monkeypatch):
        r, _, pads = renderer
        r.draw([(plain("x"),)])

        def _boom(*a):
            raise curses.error("pad refresh failed")

        monkeypatch.setattr(pads[-1], "noutrefresh", _boom)
        r.draw([(plain("x"),)])  # must not raise


@pytest.mark.tty
@pytest.mark.skipif(sys.platform == "win32", reason="pty is Unix-only")
class TestAgainstRealCurses:
    """Exercise the real curses stack inside a pty.

    Skipped on Windows, and where a terminal cannot be allocated (some CI
    sandboxes).
    """

    def test_full_render_cycle(self, modern_gpu):
        import os
        import pty

        from gtop.views import render_gpu, render_processes

        try:
            pid, fd = pty.fork()
        except OSError as exc:  # pragma: no cover - environment dependent
            pytest.skip(f"pty unavailable: {exc}")

        if pid == 0:  # child
            status = 1
            try:
                os.environ["TERM"] = "xterm"
                frame = render_gpu(modern_gpu, "|", 80) + render_processes(
                    modern_gpu, False, 80
                )

                def _session(stdscr):
                    r = CursesRenderer(stdscr)
                    r.setup()
                    r.draw(frame)
                    r.scroll(dy=3)
                    r.draw(frame)
                    r.scroll_to_bottom()
                    r.draw(frame)
                    r.scroll_to(0, 0)
                    r.draw(frame)
                    r.draw_message("status")

                curses.wrapper(_session)
                status = 0
            except BaseException:
                status = 1
            finally:
                os._exit(status)

        # Drain the master side; closing it early would hand the child EIO
        # mid-render and fail the test for the wrong reason.
        try:
            while os.read(fd, 4096):
                pass
        except OSError:
            pass  # Child exited and closed the slave end.
        finally:
            os.close(fd)

        _, status = os.waitpid(pid, 0)
        assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
