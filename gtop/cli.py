"""Argument parsing and the top-level render loop."""
from __future__ import annotations

import argparse
import sys
import time
from typing import Optional, Sequence

from .collectors import (
    CPUCollector,
    DeviceNotFoundError,
    GPUCollector,
    NvidiaSmiNotInstalledError,
)
from .terminal import clear_screen
from .views import render_cpu, render_gpu, render_processes

_FILL_CHOICES = ["*", "|", "=", "o", ".", "+"]
_DEFAULT_FILL = "\u2588"  # full block


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gtop",
        description="CPU + NVIDIA GPU monitor with colored progress bars.",
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


def _render_frame(
    args: argparse.Namespace,
    cpu: CPUCollector,
    gpu: GPUCollector,
) -> Optional[str]:
    gpu_info = gpu.collect()
    if gpu_info is None:
        return None
    parts = []
    if not args.gpu_only:
        parts.append(render_cpu(cpu.collect(), args.fill))
    parts.append(render_gpu(gpu_info, args.fill))
    parts.append(render_processes(gpu_info, args.verbose))
    return "".join(parts)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        cpu = CPUCollector()
        gpu = GPUCollector(device=args.device)
    except NvidiaSmiNotInstalledError as exc:
        print(exc, file=sys.stderr)
        return 1

    try:
        while True:
            start = time.monotonic()
            frame = _render_frame(args, cpu, gpu)
            if frame is not None:
                clear_screen()
                sys.stdout.write(frame)
                sys.stdout.flush()
            else:
                print("failed to collect GPU data; retrying...", file=sys.stderr)
            elapsed = time.monotonic() - start
            time.sleep(max(0.0, args.interval - elapsed))
    except (KeyboardInterrupt, BrokenPipeError):
        print("exit")
        return 0
    except DeviceNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    except NvidiaSmiNotInstalledError as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
