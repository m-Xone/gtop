"""Argument parsing and the curses-driven render loop."""
from __future__ import annotations

import argparse
import curses
import sys
from typing import List, Optional, Sequence

from .collectors import (
    CPUCollector,
    DeviceNotFoundError,
    GPUCollector,
    NvidiaSmiNotInstalledError,
)
from .render import CursesRenderer, Frame
from .views import render_cpu, render_gpu, render_processes
from .widgets import Line

_FILL_CHOICES = ["*", "|", "=", "o", ".", "+"]
_DEFAULT_FILL = "\u2588"  # full block

_KEYBIND_HELP = """\
keyboard controls:
  q, Q         quit
  Up / Down    scroll one line
  PgUp / PgDn  scroll one page
  Home         scroll to top
  Left / Right scroll horizontally\
"""


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gtop",
        description="CPU + NVIDIA GPU monitor with colored progress bars.",
        epilog=_KEYBIND_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "-l", "--loop", dest="interval", type=int, default=1,
        help="refresh interval (s)",
    )
    p.add_argument(
        "-i", "--index", dest="device", type=int, default=-1,
        help="display status of a single device (e.g. 'gtop -i 0')",
    )
    p.add_argument(
        "-v", "--verbose", dest="verbose", action="store_true",
        help="display full process names, including command-line arguments "
             "(may require elevated privileges)",
    )
    p.add_argument(
        "-g", "--gpu-only", dest="gpu_only", action="store_true",
        help="only display GPU stat bars (suppress CPU stat bars)",
    )
    p.add_argument(
        "-f", "--fill-char", dest="fill", type=str,
        choices=_FILL_CHOICES, default=_DEFAULT_FILL,
        help="fill char for GPU/CPU status bars",
    )
    return p


def _build_frame(
    args: argparse.Namespace,
    cpu: CPUCollector,
    gpu: GPUCollector,
    screen_width: int,
) -> Optional[Frame]:
    gpu_info = gpu.collect()
    if gpu_info is None:
        return None
    lines: List[Line] = []
    if not args.gpu_only:
        lines.extend(render_cpu(cpu.collect(), args.fill, screen_width))
    lines.extend(render_gpu(gpu_info, args.fill, screen_width))
    lines.extend(render_processes(gpu_info, args.verbose, screen_width))
    return lines


# Vertical scroll step for PgUp/PgDn relative to the visible window.
_PAGE_STEP_RATIO = 0.9
_HSCROLL_STEP = 4


def _run(stdscr, args: argparse.Namespace) -> int:
    """The inner loop, run inside :func:`curses.wrapper`."""
    try:
        cpu = CPUCollector()
        gpu = GPUCollector(device=args.device)
    except NvidiaSmiNotInstalledError as exc:
        curses.endwin()
        print(exc, file=sys.stderr)
        return 1

    renderer = CursesRenderer(stdscr)
    renderer.setup()
    stdscr.timeout(max(0, int(args.interval * 1000)))

    frame: Optional[Frame] = None
    message: Optional[str] = None
    needs_data_refresh = True

    try:
        while True:
            height, width = stdscr.getmaxyx()

            if needs_data_refresh:
                try:
                    frame = _build_frame(args, cpu, gpu, width)
                except DeviceNotFoundError as exc:
                    curses.endwin()
                    print(exc, file=sys.stderr)
                    return 1
                except NvidiaSmiNotInstalledError as exc:
                    curses.endwin()
                    print(exc, file=sys.stderr)
                    return 1
                message = (
                    None if frame is not None
                    else "failed to collect GPU data; retrying..."
                )
                needs_data_refresh = False

            if message is not None:
                renderer.draw_message(message)
            elif frame is not None:
                renderer.draw(frame)

            ch = stdscr.getch()

            if ch == -1:
                # Timeout elapsed — refresh data on the next iteration.
                needs_data_refresh = True
            elif ch in (ord("q"), ord("Q")):
                return 0
            elif ch == curses.KEY_RESIZE:
                # Next iteration picks up the new size and re-lays out.
                needs_data_refresh = True
            elif ch in (curses.KEY_DOWN, ord("j")):
                renderer.scroll(dy=1)
            elif ch in (curses.KEY_UP, ord("k")):
                renderer.scroll(dy=-1)
            elif ch == curses.KEY_NPAGE:
                renderer.scroll(dy=max(1, int(height * _PAGE_STEP_RATIO)))
            elif ch == curses.KEY_PPAGE:
                renderer.scroll(dy=-max(1, int(height * _PAGE_STEP_RATIO)))
            elif ch == curses.KEY_HOME:
                renderer.scroll_to(0, 0)
            elif ch in (curses.KEY_LEFT, ord("h")):
                renderer.scroll(dx=-_HSCROLL_STEP)
            elif ch in (curses.KEY_RIGHT, ord("l")):
                renderer.scroll(dx=_HSCROLL_STEP)
    except KeyboardInterrupt:
        return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        return curses.wrapper(_run, args)
    except curses.error as exc:
        print(f"curses initialization failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
