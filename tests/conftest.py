"""Shared fixtures: sample nvidia-smi XML and curses test doubles."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any
from xml.etree.ElementTree import Element

import pytest

# ---------------------------------------------------------------------------
# nvidia-smi XML samples
#
# The schema varies across driver versions; these cover the shapes gtop must
# tolerate. Trimmed to the elements the views actually read.
# ---------------------------------------------------------------------------

MODERN_GPU_XML = """<?xml version="1.0"?>
<nvidia_smi_log>
  <gpu id="0000:01:00.0">
    <product_name>NVIDIA GeForce RTX 4080</product_name>
    <product_architecture>Ada Lovelace</product_architecture>
    <minor_number>0</minor_number>
    <fb_memory_usage>
      <total>16384 MiB</total>
      <used>5120 MiB</used>
      <reserved>256 MiB</reserved>
    </fb_memory_usage>
    <utilization><gpu_util>73 %</gpu_util></utilization>
    <temperature><gpu_temp>62 C</gpu_temp></temperature>
    <fan_speed>45 %</fan_speed>
    <gpu_power_readings>
      <power_draw>180.25 W</power_draw>
      <current_power_limit>320.00 W</current_power_limit>
    </gpu_power_readings>
    <processes>
      <process_info>
        <pid>1</pid>
        <process_name>/usr/bin/python3</process_name>
        <used_memory>1024 MiB</used_memory>
      </process_info>
    </processes>
  </gpu>
</nvidia_smi_log>
"""

# Older drivers: <power_readings>/<power_limit> instead of the "gpu_" prefixed
# section, no <reserved> memory, no <product_architecture>.
LEGACY_GPU_XML = """<?xml version="1.0"?>
<nvidia_smi_log>
  <gpu id="0000:01:00.0">
    <product_name>Quadro NVS 5400M</product_name>
    <minor_number>0</minor_number>
    <fb_memory_usage>
      <total>2048 MiB</total>
      <used>512 MiB</used>
    </fb_memory_usage>
    <utilization><gpu_util>20 %</gpu_util></utilization>
    <temperature><gpu_temp>140 F</gpu_temp></temperature>
    <fan_speed>N/A</fan_speed>
    <power_readings>
      <power_draw>15.00 W</power_draw>
      <power_limit>45.00 W</power_limit>
    </power_readings>
    <processes>
      <process_info>
        <pid>1</pid>
        <process_name>/usr/bin/legacy</process_name>
        <used_memory>128 MiB</used_memory>
      </process_info>
    </processes>
  </gpu>
</nvidia_smi_log>
"""

# Everything that can be missing or "N/A", is.
DEGENERATE_GPU_XML = """<?xml version="1.0"?>
<nvidia_smi_log>
  <gpu id="0000:01:00.0">
    <minor_number>3</minor_number>
    <fb_memory_usage>
      <total>0 MiB</total>
      <used>0 MiB</used>
    </fb_memory_usage>
    <fan_speed>N/A</fan_speed>
    <gpu_power_readings>
      <power_draw>N/A</power_draw>
      <current_power_limit>N/A</current_power_limit>
    </gpu_power_readings>
  </gpu>
</nvidia_smi_log>
"""

# First GPU has no processes, second does. Regression guard: the process
# table must not bail out on the first empty device.
TWO_GPU_XML = """<?xml version="1.0"?>
<nvidia_smi_log>
  <gpu id="0000:01:00.0">
    <product_name>GPU Zero</product_name>
    <minor_number>0</minor_number>
    <fb_memory_usage>
      <total>8192 MiB</total>
      <used>0 MiB</used>
    </fb_memory_usage>
    <processes></processes>
  </gpu>
  <gpu id="0000:02:00.0">
    <product_name>GPU One</product_name>
    <minor_number>1</minor_number>
    <fb_memory_usage>
      <total>8192 MiB</total>
      <used>2048 MiB</used>
      <reserved>64 MiB</reserved>
    </fb_memory_usage>
    <processes>
      <process_info>
        <pid>4242</pid>
        <process_name>/opt/train.py</process_name>
        <used_memory>2048 MiB</used_memory>
      </process_info>
    </processes>
  </gpu>
</nvidia_smi_log>
"""

NO_PROCESS_XML = """<?xml version="1.0"?>
<nvidia_smi_log>
  <gpu id="0000:01:00.0">
    <minor_number>0</minor_number>
    <fb_memory_usage><total>8192 MiB</total><used>0 MiB</used></fb_memory_usage>
    <processes></processes>
  </gpu>
</nvidia_smi_log>
"""


@pytest.fixture
def modern_gpu() -> Element:
    return ET.fromstring(MODERN_GPU_XML)


@pytest.fixture
def legacy_gpu() -> Element:
    return ET.fromstring(LEGACY_GPU_XML)


@pytest.fixture
def degenerate_gpu() -> Element:
    return ET.fromstring(DEGENERATE_GPU_XML)


@pytest.fixture
def two_gpus() -> Element:
    return ET.fromstring(TWO_GPU_XML)


@pytest.fixture
def no_process_gpu() -> Element:
    return ET.fromstring(NO_PROCESS_XML)


# ---------------------------------------------------------------------------
# Curses test doubles
#
# CursesRenderer calls curses.newpad(), which needs a real terminal. These
# stubs let the placement and scroll logic be tested without one; a separate
# pty-backed test covers the real curses stack end to end.
# ---------------------------------------------------------------------------


class FakePad:
    """Records addstr placements and noutrefresh viewport arguments."""

    def __init__(self, rows: int, cols: int) -> None:
        self.rows = rows
        self.cols = cols
        self.writes: list[tuple[int, int, str, int]] = []
        self.viewports: list[tuple[int, ...]] = []
        self.erase_count = 0

    def erase(self) -> None:
        self.erase_count += 1
        self.writes.clear()

    def addstr(self, y: int, x: int, text: str, attr: int = 0) -> None:
        self.writes.append((y, x, text, attr))

    def noutrefresh(self, *args: int) -> None:
        self.viewports.append(tuple(args))


class FakeScreen:
    """Minimal stand-in for a curses stdscr window."""

    def __init__(self, height: int = 24, width: int = 80) -> None:
        self.height = height
        self.width = width
        self.messages: list[str] = []
        self.keypad_enabled = False
        self.timeout_ms: Any = None
        self.erase_count = 0
        #: Scripted keypresses for getch(); exhausting it yields "q" so a
        #: render loop under test always terminates.
        self.keys: list[int] = []

    def getch(self) -> int:
        return self.keys.pop(0) if self.keys else ord("q")

    def getmaxyx(self) -> tuple[int, int]:
        return self.height, self.width

    def keypad(self, flag: bool) -> None:
        self.keypad_enabled = flag

    def erase(self) -> None:
        self.erase_count += 1

    def noutrefresh(self) -> None:
        pass

    def refresh(self) -> None:
        pass

    def addnstr(self, y: int, x: int, text: str, n: int) -> None:
        self.messages.append(text[:n])

    def timeout(self, ms: int) -> None:
        self.timeout_ms = ms


@pytest.fixture
def make_screen():
    """Factory for :class:`FakeScreen` instances of a given size."""

    def _make(height: int = 24, width: int = 80) -> FakeScreen:
        return FakeScreen(height, width)

    return _make


@pytest.fixture
def fake_curses(monkeypatch: pytest.MonkeyPatch) -> list[FakePad]:
    """Patch the curses entry points CursesRenderer touches.

    Returns the list of pads created, so tests can inspect what was drawn.
    """
    import curses

    pads: list[FakePad] = []

    def _newpad(rows: int, cols: int) -> FakePad:
        pad = FakePad(rows, cols)
        pads.append(pad)
        return pad

    monkeypatch.setattr(curses, "newpad", _newpad)
    monkeypatch.setattr(curses, "doupdate", lambda: None)
    monkeypatch.setattr(curses, "curs_set", lambda n: 0)
    monkeypatch.setattr(curses, "has_colors", lambda: True)
    monkeypatch.setattr(curses, "start_color", lambda: None)
    monkeypatch.setattr(curses, "use_default_colors", lambda: None)
    monkeypatch.setattr(curses, "init_pair", lambda *a: None)
    # Identity-ish mapping so tests can assert which pair a segment used.
    monkeypatch.setattr(curses, "color_pair", lambda n: n << 8)
    return pads
