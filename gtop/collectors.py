"""Data collection: per-CPU usage, NVIDIA GPU telemetry, per-process metadata.

Collectors do I/O; they do not format. Views consume the plain-data values
returned here and shape them into text.
"""

from __future__ import annotations

import subprocess
import time
import xml.etree.ElementTree as ET
from typing import Protocol
from xml.etree.ElementTree import Element

import psutil


class DeviceNotFoundError(Exception):
    """Raised when ``nvidia-smi`` rejects the requested device index."""


class NvidiaSmiNotInstalledError(RuntimeError):
    """Raised when the ``nvidia-smi`` binary cannot be found on ``PATH``."""


class CPUSource(Protocol):
    """Anything that can report per-core utilization percentages."""

    def collect(self) -> list[float]: ...


class GPUSource(Protocol):
    """Anything that can report an ``nvidia-smi``-shaped XML tree.

    ``None`` signals a transient failure the caller should retry.
    """

    def collect(self) -> Element | None: ...


class CPUCollector:
    """Per-CPU utilization via :mod:`psutil`.

    ``psutil.cpu_percent`` is stateful: each call returns usage since the
    previous call. We prime it in ``__init__`` so the first ``collect()`` has
    a real baseline (the very first frame may still read close to zero).
    """

    def __init__(self) -> None:
        psutil.cpu_percent(percpu=True, interval=None)

    def collect(self) -> list[float]:
        return list(psutil.cpu_percent(percpu=True, interval=None))


class GPUCollector:
    """Runs ``nvidia-smi -q -x`` and returns the parsed XML tree.

    Returns ``None`` on transient failures (timeout, non-zero exit) so the
    render loop can retry. Permanent conditions — missing binary, invalid
    device index — raise.
    """

    def __init__(self, device: int = -1, timeout: float = 10.0) -> None:
        self._device = device
        self._timeout = timeout

    def collect(self) -> Element | None:
        args = ["nvidia-smi", "-q", "-x"]
        if self._device >= 0:
            args += ["-i", str(self._device)]

        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise NvidiaSmiNotInstalledError("nvidia-smi not detected") from exc
        except subprocess.TimeoutExpired:
            return None

        if result.returncode == 0:
            return ET.fromstring(result.stdout)
        if result.returncode == 6:
            raise DeviceNotFoundError(f"device {self._device} not found")
        return None


def process_name(pid: int, verbose: bool = True) -> str:
    """Return a human-readable process name.

    When *verbose* is True the full argv is returned; otherwise the executable
    path (falling back to the short name) is used.
    """
    try:
        proc = psutil.Process(int(pid))
        with proc.oneshot():
            if verbose:
                cmdline = proc.cmdline()
                if cmdline:
                    return " ".join(cmdline)
            return proc.exe() or proc.name()
    except psutil.AccessDenied:
        return "Permission Denied"
    except (psutil.NoSuchProcess, ValueError):
        return "unavailable"


def process_cpu_percent(pid: int) -> float | None:
    """Return the process's lifetime CPU%, equivalent to ``ps -o %cpu``.

    Computed as ``(user + system) / elapsed * 100`` against wall clock. Returns
    ``None`` if the process has vanished or is not accessible.
    """
    try:
        proc = psutil.Process(int(pid))
        with proc.oneshot():
            times = proc.cpu_times()
            created = proc.create_time()
        elapsed = max(1e-6, time.time() - created)
        return round(100.0 * (times.user + times.system) / elapsed, 1)
    except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
        return None
