"""CLI: argument contract, frame assembly, and key dispatch."""

from __future__ import annotations

import argparse
import curses

import pytest

from gtop.cli import (
    BLOCK_CHAR,
    FILL_CHOICES,
    Action,
    _build_parser,
    build_frame,
    handle_key,
    main,
)
from gtop.collectors import DeviceNotFoundError, NvidiaSmiNotInstalledError
from gtop.render import HSCROLL_STEP, CursesRenderer
from gtop.widgets import plain


@pytest.fixture
def parser():
    return _build_parser()


class TestArgumentContract:
    """These flags are the project's public surface; they must not drift."""

    def test_defaults(self, parser):
        args = parser.parse_args([])
        assert (args.interval, args.device, args.verbose, args.gpu_only, args.fill) == (
            1,
            -1,
            False,
            False,
            BLOCK_CHAR,
        )

    def test_long_forms(self, parser):
        args = parser.parse_args(
            [
                "--loop",
                "5",
                "--index",
                "2",
                "--verbose",
                "--gpu-only",
                "--fill-char",
                "=",
            ]
        )
        assert (args.interval, args.device, args.verbose, args.gpu_only, args.fill) == (
            5,
            2,
            True,
            True,
            "=",
        )

    def test_short_forms(self, parser):
        args = parser.parse_args(["-l", "5", "-i", "2", "-v", "-g", "-f", "="])
        assert (args.interval, args.device, args.verbose, args.gpu_only, args.fill) == (
            5,
            2,
            True,
            True,
            "=",
        )

    @pytest.mark.parametrize("char", FILL_CHOICES)
    def test_every_documented_fill_char_is_accepted(self, parser, char):
        assert parser.parse_args(["-f", char]).fill == char

    def test_the_default_fill_char_is_a_valid_explicit_choice(self, parser):
        """Regression: the default block char used to be rejected by -f."""
        assert BLOCK_CHAR in FILL_CHOICES
        assert parser.parse_args(["-f", BLOCK_CHAR]).fill == BLOCK_CHAR

    def test_unknown_fill_char_is_rejected(self, parser):
        with pytest.raises(SystemExit):
            parser.parse_args(["-f", "@"])

    def test_non_integer_interval_is_rejected(self, parser):
        with pytest.raises(SystemExit):
            parser.parse_args(["-l", "abc"])

    def test_help_documents_the_keybindings(self, parser):
        help_text = parser.format_help()
        for token in ("q, Q", "PgUp", "Home", "scroll"):
            assert token in help_text


class FakeCPU:
    def __init__(self, usage=None):
        self.usage = usage if usage is not None else [10.0, 20.0]
        self.calls = 0

    def collect(self):
        self.calls += 1
        return self.usage


class FakeGPU:
    def __init__(self, root):
        self.root = root
        self.calls = 0

    def collect(self):
        self.calls += 1
        return self.root


def _args(**overrides):
    base = {
        "interval": 1,
        "device": -1,
        "verbose": False,
        "gpu_only": False,
        "fill": "|",
    }
    base.update(overrides)
    return argparse.Namespace(**base)


class TestBuildFrame:
    def test_returns_none_when_the_gpu_read_fails(self):
        assert build_frame(_args(), FakeCPU(), FakeGPU(None), 80) is None

    def test_includes_cpu_gpu_and_process_sections(self, modern_gpu):
        frame = build_frame(_args(), FakeCPU(), FakeGPU(modern_gpu), 96)
        assert frame is not None
        text = "\n".join("".join(s.text for s in line) for line in frame)
        assert "CPU 0" in text
        assert "NVIDIA GeForce RTX 4080" in text
        assert "Process ID" in text

    def test_gpu_only_suppresses_the_cpu_panel(self, modern_gpu):
        cpu = FakeCPU()
        frame = build_frame(_args(gpu_only=True), cpu, FakeGPU(modern_gpu), 96)
        assert frame is not None
        text = "\n".join("".join(s.text for s in line) for line in frame)
        assert "CPU 0" not in text
        assert cpu.calls == 0, "CPU must not be sampled when suppressed"

    def test_samples_the_gpu_once_per_frame(self, modern_gpu):
        gpu = FakeGPU(modern_gpu)
        build_frame(_args(), FakeCPU(), gpu, 96)
        assert gpu.calls == 1

    def test_layout_reacts_to_screen_width(self, modern_gpu):
        wide = build_frame(_args(), FakeCPU(), FakeGPU(modern_gpu), 200)
        narrow = build_frame(_args(), FakeCPU(), FakeGPU(modern_gpu), 40)
        width_of = lambda f: sum(len(s.text) for s in f[0])  # noqa: E731
        assert width_of(wide) > width_of(narrow)


@pytest.fixture
def key_renderer(fake_curses, make_screen):
    r = CursesRenderer(make_screen(height=10, width=40))
    r.setup()
    r.draw([(plain(f"line {i}"),) for i in range(100)])
    return r


class TestKeyDispatch:
    def test_timeout_sentinel_triggers_a_refresh(self, key_renderer):
        assert handle_key(-1, key_renderer) is Action.REFRESH

    def test_resize_triggers_a_refresh(self, key_renderer):
        assert handle_key(curses.KEY_RESIZE, key_renderer) is Action.REFRESH

    @pytest.mark.parametrize("key", ["q", "Q"])
    def test_quit_keys(self, key_renderer, key):
        assert handle_key(ord(key), key_renderer) is Action.QUIT

    def test_unbound_keys_do_nothing(self, key_renderer):
        before = key_renderer.scroll_offset
        assert handle_key(ord("z"), key_renderer) is Action.NONE
        assert key_renderer.scroll_offset == before

    @pytest.mark.parametrize("key", [curses.KEY_DOWN, ord("j")])
    def test_scroll_down_one_line(self, key_renderer, key):
        handle_key(key, key_renderer)
        assert key_renderer.scroll_offset[0] == 1

    @pytest.mark.parametrize("key", [curses.KEY_UP, ord("k")])
    def test_scroll_up_one_line(self, key_renderer, key):
        key_renderer.scroll_to(5, 0)
        handle_key(key, key_renderer)
        assert key_renderer.scroll_offset[0] == 4

    def test_page_down_moves_about_a_screen(self, key_renderer):
        handle_key(curses.KEY_NPAGE, key_renderer)
        assert key_renderer.scroll_offset[0] == key_renderer.page_size()

    def test_page_up_moves_back(self, key_renderer):
        key_renderer.scroll_to(50, 0)
        handle_key(curses.KEY_PPAGE, key_renderer)
        assert key_renderer.scroll_offset[0] == 50 - key_renderer.page_size()

    def test_home_returns_to_the_origin(self, key_renderer):
        key_renderer.scroll_to(40, 8)
        handle_key(curses.KEY_HOME, key_renderer)
        assert key_renderer.scroll_offset == (0, 0)

    def test_end_jumps_to_the_bottom(self, key_renderer):
        handle_key(curses.KEY_END, key_renderer)
        assert key_renderer.scroll_offset[0] == 100 - 10

    @pytest.mark.parametrize("key", [curses.KEY_RIGHT, ord("l")])
    def test_scroll_right(self, key_renderer, key):
        key_renderer.draw([(plain("x" * 500),)])
        handle_key(key, key_renderer)
        assert key_renderer.scroll_offset[1] == HSCROLL_STEP

    @pytest.mark.parametrize("key", [curses.KEY_LEFT, ord("h")])
    def test_scroll_left(self, key_renderer, key):
        key_renderer.draw([(plain("x" * 500),)])
        key_renderer.scroll_to(0, 20)
        handle_key(key, key_renderer)
        assert key_renderer.scroll_offset[1] == 20 - HSCROLL_STEP

    def test_scroll_keys_do_not_force_a_data_refresh(self, key_renderer):
        """Scrolling must repaint from the cached frame, not re-poll the GPU."""
        for key in (curses.KEY_DOWN, curses.KEY_UP, curses.KEY_NPAGE, curses.KEY_HOME):
            assert handle_key(key, key_renderer) is Action.NONE


class TestRunLoop:
    """Drive the real loop with a scripted key sequence."""

    @pytest.fixture
    def run_loop(self, fake_curses, make_screen, monkeypatch, modern_gpu):
        from gtop import cli

        state = {"gpu_returns": modern_gpu}
        cpu = FakeCPU()
        gpu = FakeGPU(modern_gpu)

        def _gpu_collect():
            gpu.calls += 1
            return state["gpu_returns"]

        gpu.collect = _gpu_collect  # type: ignore[method-assign]
        monkeypatch.setattr(cli, "CPUCollector", lambda: cpu)
        monkeypatch.setattr(cli, "GPUCollector", lambda device: gpu)

        def _run(keys, **arg_overrides):
            screen = make_screen(height=10, width=80)
            screen.keys = list(keys)
            code = cli._run(screen, _args(**arg_overrides))
            return code, screen, cpu, gpu, state

        return _run

    def test_quit_key_exits_cleanly(self, run_loop):
        code, *_ = run_loop([ord("q")])
        assert code == 0

    def test_first_frame_is_drawn_before_any_input(self, run_loop):
        _, _, _, gpu, _ = run_loop([ord("q")])
        assert gpu.calls == 1

    def test_timeout_sentinel_polls_again(self, run_loop):
        _, _, _, gpu, _ = run_loop([-1, -1, ord("q")])
        assert gpu.calls == 3

    def test_scrolling_repaints_without_re_polling(self, run_loop):
        _, _, _, gpu, _ = run_loop([curses.KEY_DOWN, curses.KEY_DOWN, ord("q")])
        assert gpu.calls == 1, "scroll keys must reuse the cached frame"

    def test_resize_forces_a_fresh_layout(self, run_loop):
        _, _, _, gpu, _ = run_loop([curses.KEY_RESIZE, ord("q")])
        assert gpu.calls == 2

    def test_recovers_after_a_transient_collection_failure(
        self, fake_curses, make_screen, monkeypatch, modern_gpu
    ):
        """A failed poll shows a message; the next good poll renders normally."""
        from gtop import cli

        results = [None, modern_gpu]

        class FlakyGPU:
            def collect(self):
                return results.pop(0) if results else modern_gpu

        monkeypatch.setattr(cli, "CPUCollector", lambda: FakeCPU())
        monkeypatch.setattr(cli, "GPUCollector", lambda device: FlakyGPU())
        screen = make_screen(height=10, width=80)
        screen.keys = [-1, ord("q")]  # first frame fails, second succeeds

        assert cli._run(screen, _args()) == 0
        assert len(screen.messages) == 1, "only the failed frame shows a message"
        assert "failed to collect GPU data" in screen.messages[0]

    def test_message_is_shown_when_the_gpu_read_fails(
        self, fake_curses, make_screen, monkeypatch
    ):
        from gtop import cli

        monkeypatch.setattr(cli, "CPUCollector", lambda: FakeCPU())
        monkeypatch.setattr(cli, "GPUCollector", lambda device: FakeGPU(None))
        screen = make_screen(height=10, width=80)
        screen.keys = [ord("q")]
        assert cli._run(screen, _args()) == 0
        assert screen.messages
        assert "failed to collect GPU data" in screen.messages[0]

    def test_refresh_interval_is_applied_as_the_input_timeout(self, run_loop):
        _, screen, _, _, _ = run_loop([ord("q")], interval=3)
        assert screen.timeout_ms == 3000

    def test_gpu_only_never_samples_the_cpu(self, run_loop):
        _, _, cpu, _, _ = run_loop([-1, -1, ord("q")], gpu_only=True)
        assert cpu.calls == 0


def _run_help(env_extra=None):
    """Run ``python -m gtop --help`` in a subprocess and return the result."""
    import os
    import subprocess
    import sys

    env = dict(os.environ)
    env.pop("PYTHONIOENCODING", None)
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, "-m", "gtop", "--help"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        env=env,
    )


class TestModuleEntryPoint:
    def test_python_dash_m_gtop_runs(self):
        result = _run_help()
        assert result.returncode == 0, result.stderr
        assert "usage: gtop" in result.stdout

    def test_help_lists_the_block_fill_char(self):
        assert BLOCK_CHAR in _run_help().stdout

    def test_help_survives_a_legacy_single_byte_code_page(self):
        """Regression: piping --help on Windows died on the block char.

        Windows uses the ANSI code page for redirected stdout, and cp1252
        cannot encode U+2588. PYTHONIOENCODING reproduces that here on any
        platform.
        """
        result = _run_help({"PYTHONIOENCODING": "cp1252"})
        assert result.returncode == 0, result.stderr
        assert "UnicodeEncodeError" not in result.stderr
        assert "usage: gtop" in result.stdout

    @pytest.mark.parametrize("encoding", ["cp1252", "cp437", "ascii", "latin-1"])
    def test_help_survives_any_ascii_compatible_encoding(self, encoding):
        result = _run_help({"PYTHONIOENCODING": encoding})
        assert result.returncode == 0, result.stderr


class TestMainErrorPaths:
    def test_missing_nvidia_smi_exits_nonzero(self, monkeypatch, capsys):
        def _wrapper(fn, *a, **kw):
            raise NvidiaSmiNotInstalledError("nvidia-smi not detected")

        monkeypatch.setattr(curses, "wrapper", _wrapper)
        assert main([]) == 1
        assert "nvidia-smi not detected" in capsys.readouterr().err

    def test_bad_device_exits_nonzero(self, monkeypatch, capsys):
        def _wrapper(fn, *a, **kw):
            raise DeviceNotFoundError("device 9 not found")

        monkeypatch.setattr(curses, "wrapper", _wrapper)
        assert main([]) == 1
        assert "device 9 not found" in capsys.readouterr().err

    def test_curses_failure_is_reported_cleanly(self, monkeypatch, capsys):
        def _wrapper(fn, *a, **kw):
            raise curses.error("setupterm failed")

        monkeypatch.setattr(curses, "wrapper", _wrapper)
        assert main([]) == 1
        assert "curses initialization failed" in capsys.readouterr().err

    def test_interrupt_exits_zero(self, monkeypatch):
        def _wrapper(fn, *a, **kw):
            raise KeyboardInterrupt

        monkeypatch.setattr(curses, "wrapper", _wrapper)
        assert main([]) == 0

    def test_clean_exit_propagates_the_return_code(self, monkeypatch):
        monkeypatch.setattr(curses, "wrapper", lambda fn, *a, **kw: 0)
        assert main([]) == 0
