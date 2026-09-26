"""Collectors: subprocess/psutil boundaries are mocked, no real GPU needed."""

from __future__ import annotations

import subprocess

import psutil
import pytest

from gtop import collectors
from gtop.collectors import (
    CPUCollector,
    DeviceNotFoundError,
    GPUCollector,
    NvidiaSmiNotInstalledError,
    process_cpu_percent,
    process_name,
)


class FakeCompleted:
    def __init__(self, returncode: int, stdout: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = ""


MINIMAL_XML = (
    "<nvidia_smi_log><gpu><minor_number>0</minor_number></gpu></nvidia_smi_log>"
)


class TestCPUCollector:
    def test_returns_one_reading_per_core(self, monkeypatch):
        monkeypatch.setattr(psutil, "cpu_percent", lambda **kw: [1.0, 2.0, 3.0])
        assert CPUCollector().collect() == [1.0, 2.0, 3.0]

    def test_primes_psutil_on_construction(self, monkeypatch):
        calls = []

        def _cpu_percent(**kw):
            calls.append(kw)
            return [0.0]

        monkeypatch.setattr(psutil, "cpu_percent", _cpu_percent)
        CPUCollector()
        assert calls, "constructor must prime psutil's stateful counter"
        assert calls[0]["percpu"] is True

    def test_collect_returns_a_list_not_psutils_internal(self, monkeypatch):
        source = [5.0]
        monkeypatch.setattr(psutil, "cpu_percent", lambda **kw: source)
        result = CPUCollector().collect()
        result.append(99.0)
        assert source == [5.0]


class TestGPUCollectorArgs:
    def test_all_devices_by_default(self, monkeypatch):
        seen = {}

        def _run(args, **kw):
            seen["args"] = args
            return FakeCompleted(0, MINIMAL_XML)

        monkeypatch.setattr(subprocess, "run", _run)
        GPUCollector().collect()
        assert seen["args"] == ["nvidia-smi", "-q", "-x"]

    def test_single_device_appends_index(self, monkeypatch):
        seen = {}

        def _run(args, **kw):
            seen["args"] = args
            return FakeCompleted(0, MINIMAL_XML)

        monkeypatch.setattr(subprocess, "run", _run)
        GPUCollector(device=2).collect()
        assert seen["args"] == ["nvidia-smi", "-q", "-x", "-i", "2"]

    def test_timeout_is_passed_through(self, monkeypatch):
        seen = {}

        def _run(args, **kw):
            seen.update(kw)
            return FakeCompleted(0, MINIMAL_XML)

        monkeypatch.setattr(subprocess, "run", _run)
        GPUCollector(timeout=3.5).collect()
        assert seen["timeout"] == 3.5


class TestGPUCollectorOutcomes:
    def test_success_returns_parsed_xml(self, monkeypatch):
        monkeypatch.setattr(
            subprocess, "run", lambda *a, **kw: FakeCompleted(0, MINIMAL_XML)
        )
        root = GPUCollector().collect()
        assert root is not None
        node = root.find(".//gpu/minor_number")
        assert node is not None
        assert node.text == "0"

    def test_missing_binary_raises(self, monkeypatch):
        def _run(*a, **kw):
            raise FileNotFoundError("nvidia-smi")

        monkeypatch.setattr(subprocess, "run", _run)
        with pytest.raises(NvidiaSmiNotInstalledError):
            GPUCollector().collect()

    def test_bad_device_index_raises(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: FakeCompleted(6))
        with pytest.raises(DeviceNotFoundError):
            GPUCollector(device=9).collect()

    def test_timeout_is_transient_and_returns_none(self, monkeypatch):
        def _run(*a, **kw):
            raise subprocess.TimeoutExpired(cmd="nvidia-smi", timeout=1)

        monkeypatch.setattr(subprocess, "run", _run)
        assert GPUCollector().collect() is None

    def test_other_failures_return_none(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: FakeCompleted(1))
        assert GPUCollector().collect() is None


class FakeProcess:
    """Stands in for psutil.Process."""

    def __init__(self, cmdline=None, exe="", name="", times=None, created=0.0):
        self._cmdline = cmdline or []
        self._exe = exe
        self._name = name
        self._times = times
        self._created = created

    def oneshot(self):
        class _Ctx:
            def __enter__(self_inner):
                return None

            def __exit__(self_inner, *a):
                return False

        return _Ctx()

    def cmdline(self):
        return self._cmdline

    def exe(self):
        return self._exe

    def name(self):
        return self._name

    def cpu_times(self):
        return self._times

    def create_time(self):
        return self._created


class Times:
    def __init__(self, user: float, system: float) -> None:
        self.user = user
        self.system = system


class TestProcessName:
    def test_verbose_joins_the_full_command_line(self, monkeypatch):
        monkeypatch.setattr(
            collectors.psutil,
            "Process",
            lambda pid: FakeProcess(cmdline=["python", "train.py", "--epochs=3"]),
        )
        assert process_name(1, verbose=True) == "python train.py --epochs=3"

    def test_non_verbose_prefers_the_executable_path(self, monkeypatch):
        monkeypatch.setattr(
            collectors.psutil,
            "Process",
            lambda pid: FakeProcess(cmdline=["python", "x.py"], exe="/usr/bin/python3"),
        )
        assert process_name(1, verbose=False) == "/usr/bin/python3"

    def test_verbose_falls_back_to_exe_when_cmdline_is_empty(self, monkeypatch):
        monkeypatch.setattr(
            collectors.psutil,
            "Process",
            lambda pid: FakeProcess(cmdline=[], exe="/usr/bin/kthread"),
        )
        assert process_name(1, verbose=True) == "/usr/bin/kthread"

    def test_falls_back_to_short_name_when_exe_is_empty(self, monkeypatch):
        monkeypatch.setattr(
            collectors.psutil,
            "Process",
            lambda pid: FakeProcess(cmdline=[], exe="", name="kworker"),
        )
        assert process_name(1, verbose=True) == "kworker"

    def test_access_denied_is_reported_distinctly(self, monkeypatch):
        def _raise(pid):
            raise psutil.AccessDenied(pid)

        monkeypatch.setattr(collectors.psutil, "Process", _raise)
        assert process_name(1) == "Permission Denied"

    def test_vanished_process_is_unavailable(self, monkeypatch):
        def _raise(pid):
            raise psutil.NoSuchProcess(pid)

        monkeypatch.setattr(collectors.psutil, "Process", _raise)
        assert process_name(1) == "unavailable"

    def test_non_numeric_pid_is_unavailable(self, monkeypatch):
        assert process_name("not-a-pid") == "unavailable"  # type: ignore[arg-type]


class TestProcessCpuPercent:
    def test_computes_cpu_time_over_elapsed_wall_clock(self, monkeypatch):
        monkeypatch.setattr(
            collectors.psutil,
            "Process",
            lambda pid: FakeProcess(
                times=Times(user=25.0, system=25.0), created=1000.0
            ),
        )
        monkeypatch.setattr(collectors.time, "time", lambda: 1100.0)
        # 50s of CPU over 100s elapsed == 50%
        assert process_cpu_percent(1) == 50.0

    def test_result_is_rounded_to_one_decimal(self, monkeypatch):
        monkeypatch.setattr(
            collectors.psutil,
            "Process",
            lambda pid: FakeProcess(times=Times(user=1.0, system=0.0), created=1000.0),
        )
        monkeypatch.setattr(collectors.time, "time", lambda: 1003.0)
        assert process_cpu_percent(1) == 33.3

    def test_zero_elapsed_does_not_divide_by_zero(self, monkeypatch):
        monkeypatch.setattr(
            collectors.psutil,
            "Process",
            lambda pid: FakeProcess(times=Times(user=0.0, system=0.0), created=1000.0),
        )
        monkeypatch.setattr(collectors.time, "time", lambda: 1000.0)
        assert process_cpu_percent(1) == 0.0

    def test_vanished_process_returns_none(self, monkeypatch):
        def _raise(pid):
            raise psutil.NoSuchProcess(pid)

        monkeypatch.setattr(collectors.psutil, "Process", _raise)
        assert process_cpu_percent(1) is None

    def test_access_denied_returns_none(self, monkeypatch):
        def _raise(pid):
            raise psutil.AccessDenied(pid)

        monkeypatch.setattr(collectors.psutil, "Process", _raise)
        assert process_cpu_percent(1) is None


class TestRealProcess:
    """A couple of unmocked calls against this interpreter's own process."""

    def test_own_process_name_is_resolvable(self):
        import os

        assert process_name(os.getpid(), verbose=True)

    def test_own_cpu_percent_is_a_sane_number(self):
        import os

        pct = process_cpu_percent(os.getpid())
        assert pct is not None
        assert 0.0 <= pct <= 100.0 * (os.cpu_count() or 1)
