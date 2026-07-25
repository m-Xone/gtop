"""Argument parsing and the curses-driven render loop."""

from __future__ import annotations

import argparse
import curses
import sys
from collections.abc import Sequence
from enum import Enum

from .collectors import (
    CPUCollector,
    CPUSource,
    DeviceNotFoundError,
    GPUCollector,
    GPUSource,
    NvidiaSmiNotInstalledError,
)
from .render import HSCROLL_STEP, CursesRenderer, Frame
from .views import render_cpu, render_gpu, render_processes
from .widgets import Line

#: Full block, the default bar fill.
BLOCK_CHAR = "█"

#: Accepted values for ``--fill-char``. The default is included so that
#: passing it explicitly is valid.
FILL_CHOICES = [BLOCK_CHAR, "*", "|", "=", "o", ".", "+"]

_KEYBIND_HELP = """\
keyboard controls:
  q, Q            quit
  Up/Down, k/j    scroll one line
  PgUp / PgDn     scroll one page
  Home / End      jump to top / bottom
  Left/Right, h/l scroll horizontally\
"""


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gtop",
        description="CPU + NVIDIA GPU monitor with colored progress bars.",
        epilog=_KEYBIND_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "-l",
        "--loop",
        dest="interval",
        type=int,
        default=1,
        help="refresh interval (s)",
    )
    p.add_argument(
        "-i",
        "--index",
        dest="device",
        type=int,
        default=-1,
        help="display status of a single device (e.g. 'gtop -i 0')",
    )
    p.add_argument(
        "-v",
        "--verbose",
        dest="verbose",
        action="store_true",
        help="display full process names, including command-line arguments "
        "(may require elevated privileges)",
    )
    p.add_argument(
        "-g",
        "--gpu-only",
        dest="gpu_only",
        action="store_true",
        help="only display GPU stat bars (suppress CPU stat bars)",
    )
    p.add_argument(
        "-f",
        "--fill-char",
        dest="fill",
        type=str,
        choices=FILL_CHOICES,
        default=BLOCK_CHAR,
        help="fill char for GPU/CPU status bars",
    )
    return p


def build_frame(
    args: argparse.Namespace,
    cpu: CPUSource,
    gpu: GPUSource,
    screen_width: int,
) -> Frame | None:
    """Collect a fresh sample and lay it out, or ``None`` if the GPU read failed."""
    gpu_info = gpu.collect()
    if gpu_info is None:
        return None
    lines: list[Line] = []
    if not args.gpu_only:
        lines.extend(render_cpu(cpu.collect(), args.fill, screen_width))
    lines.extend(render_gpu(gpu_info, args.fill, screen_width))
    lines.extend(render_processes(gpu_info, args.verbose, screen_width))
    return lines


class Action(Enum):
    """What the loop should do after handling a keypress."""

    NONE = "none"
    QUIT = "quit"
    REFRESH = "refresh"


def handle_key(ch: int, renderer: CursesRenderer) -> Action:
    """Apply a keypress to *renderer* and report what the loop should do next.

    ``-1`` is curses' "no input before timeout" sentinel, which is what
    drives the periodic refresh.
    """
    if ch == -1:
        return Action.REFRESH
    if ch in (ord("q"), ord("Q")):
        return Action.QUIT
    if ch == curses.KEY_RESIZE:
        return Action.REFRESH
    if ch in (curses.KEY_DOWN, ord("j")):
        renderer.scroll(dy=1)
    elif ch in (curses.KEY_UP, ord("k")):
        renderer.scroll(dy=-1)
    elif ch == curses.KEY_NPAGE:
        renderer.scroll(dy=renderer.page_size())
    elif ch == curses.KEY_PPAGE:
        renderer.scroll(dy=-renderer.page_size())
    elif ch == curses.KEY_HOME:
        renderer.scroll_to(0, 0)
    elif ch == curses.KEY_END:
        renderer.scroll_to_bottom()
    elif ch in (curses.KEY_LEFT, ord("h")):
        renderer.scroll(dx=-HSCROLL_STEP)
    elif ch in (curses.KEY_RIGHT, ord("l")):
        renderer.scroll(dx=HSCROLL_STEP)
    return Action.NONE


def _run(stdscr: curses.window, args: argparse.Namespace) -> int:
    """The render loop, run inside :func:`curses.wrapper`."""
    cpu = CPUCollector()
    gpu = GPUCollector(device=args.device)

    renderer = CursesRenderer(stdscr)
    renderer.setup()
    stdscr.timeout(max(0, int(args.interval * 1000)))

    frame: Frame | None = None
    message: str | None = None
    needs_refresh = True

    while True:
        if needs_refresh:
            frame = build_frame(args, cpu, gpu, stdscr.getmaxyx()[1])
            message = (
                None if frame is not None else "failed to collect GPU data; retrying..."
            )
            needs_refresh = False

        if message is not None:
            renderer.draw_message(message)
        elif frame is not None:
            renderer.draw(frame)

        action = handle_key(stdscr.getch(), renderer)
        if action is Action.QUIT:
            return 0
        if action is Action.REFRESH:
            needs_refresh = True


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        return curses.wrapper(_run, args)
    except (DeviceNotFoundError, NvidiaSmiNotInstalledError) as exc:
        print(exc, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    except curses.error as exc:
        print(f"curses initialization failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
