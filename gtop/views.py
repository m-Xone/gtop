"""Panel renderers: turn collector output into formatted text blocks."""
from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple
from xml.etree.ElementTree import Element

from .collectors import process_cpu_percent, process_name
from .terminal import ProgressBar, hrule, row

# ---------------------------------------------------------------------------
# GPU layout constants
# ---------------------------------------------------------------------------

# nvidia-smi's XML schema has changed across driver versions. Power metrics
# may live in either ``<gpu_power_readings>`` or ``<power_readings>``, each
# with slightly different child tags. Candidates are tried in order.
_POWER_SECTIONS: Tuple[Tuple[str, str, str], ...] = (
    # (section_tag, draw_tag, limit_tag)
    ("gpu_power_readings", "power_draw", "current_power_limit"),
    ("power_readings", "power_draw", "power_limit"),
)

_FRAME_WIDTH = 96


def _unavailable(label: str, title_w: int = 16) -> str:
    return f"{label[:title_w].ljust(title_w)} [data not available]\n"


# ---------------------------------------------------------------------------
# CPU panel
# ---------------------------------------------------------------------------

def _cpu_grid(n: int) -> Tuple[int, int]:
    """Return ``(columns, bar_length)`` sized for the number of cores."""
    if n > 24:
        return 4, 12
    if n > 16:
        return 3, 20
    return 2, 35


def render_cpu(usage: Sequence[float], fill_char: str) -> str:
    if not usage:
        return ""

    n_cols, bar_length = _cpu_grid(len(usage))
    out: List[str] = [hrule(_FRAME_WIDTH), "\n"]
    for i, pct in enumerate(usage):
        out.append(
            ProgressBar(
                title=f"CPU {i}",
                pct=pct / 100.0,
                title_w=6,
                fill_char=fill_char,
                bar_length=bar_length,
                unit="%",
                separator="",
            ).render()
        )
        if (i + 1) % n_cols == 0:
            out.append("\n")
    out.append("\n\n")
    return "".join(out)


# ---------------------------------------------------------------------------
# GPU panel — one block per detected device
# ---------------------------------------------------------------------------

def _memory_bar(gpu: Element, fill_char: str) -> str:
    try:
        mem = gpu.find("fb_memory_usage")
        total = int(mem.find("total").text.split()[0])
        used = int(mem.find("used").text.split()[0])
        reserved_elt = mem.find("reserved")
        reserved = (
            int(reserved_elt.text.split()[0]) if reserved_elt is not None else 0
        )
        if total <= 0:
            raise ValueError
        return ProgressBar(
            title="Memory Usage",
            pct=(used + reserved) / total,
            fill_char=fill_char,
            unit="%",
            epilogue=f"{used + reserved} MiB/{total} MiB",
        ).render()
    except Exception:
        return _unavailable("Memory Usage")


def _utilization_bar(gpu: Element, fill_char: str) -> str:
    try:
        util = int(gpu.find("utilization").find("gpu_util").text.rstrip("%"))
        return ProgressBar(
            title="Utilization",
            pct=max(0, min(util, 100)) / 100.0,
            fill_char=fill_char,
            unit="%",
        ).render()
    except Exception:
        return _unavailable("Utilization")


def _power_bar(gpu: Element, fill_char: str) -> str:
    try:
        for section, draw_tag, limit_tag in _POWER_SECTIONS:
            node = gpu.find(section)
            if node is None:
                continue
            draw_txt = node.find(draw_tag).text
            limit_txt = node.find(limit_tag).text
            if draw_txt == "N/A" or limit_txt == "N/A":
                raise ValueError
            draw = float(draw_txt.split()[0])
            limit = float(limit_txt.split()[0])
            if limit <= 0:
                raise ValueError
            return ProgressBar(
                title="Power Usage",
                pct=draw / limit,
                fill_char=fill_char,
                unit="%",
                epilogue=f"{draw} W/{limit} W",
            ).render()
        raise ValueError  # no matching power section
    except Exception:
        return _unavailable("Power Usage")


def _temperature_bar(gpu: Element, fill_char: str) -> str:
    try:
        node = gpu.find("temperature").find("gpu_temp")
        temp_txt = node.text.split()
        temp = int(temp_txt[0])
        scale = temp_txt[1]
        temp_scale = 100 if scale == "C" else 212
        return ProgressBar(
            title="Temperature",
            pct=temp / temp_scale,
            fill_char=fill_char,
            thresholds=(0.6, 0.7),
            unit=scale,
            epilogue=f"{temp} {scale}",
        ).render()
    except Exception:
        return _unavailable("Temperature")


def _fan_bar(gpu: Element, fill_char: str) -> str:
    try:
        txt = gpu.find("fan_speed").text
        if txt == "N/A":
            raise ValueError
        return ProgressBar(
            title="Fan Speed",
            pct=int(txt.split()[0]) / 100.0,
            fill_char=fill_char,
            thresholds=(0.5, 0.75),
            unit="%",
        ).render()
    except Exception:
        return _unavailable("Fan Speed")


def _gpu_header(gpu: Element) -> str:
    gpu_id = gpu.find("minor_number").text
    name_elt = gpu.find("product_name")
    arch_elt = gpu.find("product_architecture")
    if name_elt is not None and name_elt.text:
        arch = (
            f"({arch_elt.text})"
            if arch_elt is not None and arch_elt.text
            else ""
        )
        return f"GPU {gpu_id}: {name_elt.text} {arch}\n"
    return f"GPU {gpu_id}\n"


def render_gpu(gpu_info: Element, fill_char: str) -> str:
    out: List[str] = []
    for gpu in gpu_info.findall(".//gpu"):
        out.extend(
            [
                hrule(_FRAME_WIDTH), "\n",
                _gpu_header(gpu),
                _utilization_bar(gpu, fill_char),
                _memory_bar(gpu, fill_char),
                _power_bar(gpu, fill_char),
                _temperature_bar(gpu, fill_char),
                _fan_bar(gpu, fill_char),
                hrule(_FRAME_WIDTH), "\n",
            ]
        )
    return "".join(out)


# ---------------------------------------------------------------------------
# Process table
# ---------------------------------------------------------------------------

_NAME_WIDTH = 50
_PROC_WIDTHS: Tuple[int, ...] = (6, 10, _NAME_WIDTH, 7, 11)
_PROC_HEADERS: Tuple[str, ...] = ("GPU ID", "Process ID", "Name", "CPU %", "GPU Mem")


def _truncate_name(name: str) -> str:
    """Middle-ellipsize to keep the first 23 and tail portion of a long name."""
    if len(name) <= _NAME_WIDTH:
        return name
    return name[:23] + "..." + name[26:_NAME_WIDTH]


def _iter_proc_rows(gpu: Element, verbose: bool) -> Iterable[Tuple[str, ...]]:
    gpu_id = gpu.find("minor_number").text
    mem = gpu.find("fb_memory_usage")

    reserved_elt = mem.find("reserved") if mem is not None else None
    if reserved_elt is not None:
        yield gpu_id, "N/A", "[reserved]", "N/A", reserved_elt.text

    for proc in gpu.findall("processes/process_info"):
        pid_txt = proc.find("pid").text
        try:
            pid = int(pid_txt)
        except (TypeError, ValueError):
            continue

        cpu_pct = process_cpu_percent(pid)
        cpu_cell = "N/A" if cpu_pct is None else str(cpu_pct)

        if verbose:
            name = process_name(pid, verbose=True)
        else:
            name_elt = proc.find("process_name")
            name = (
                name_elt.text
                if name_elt is not None and name_elt.text
                else "unavailable"
            )

        used_mem = proc.find("used_memory").text
        yield gpu_id, pid_txt, _truncate_name(name), cpu_cell, used_mem


def render_processes(gpu_info: Element, verbose: bool = False) -> str:
    gpus = gpu_info.findall(".//gpu")
    if not any(gpu.findall("processes/process_info") for gpu in gpus):
        return "Process data unavailable\n"

    out: List[str] = [
        hrule(_FRAME_WIDTH), "\n",
        row(_PROC_HEADERS, _PROC_WIDTHS),
        row(
            tuple(hrule(w) for w in _PROC_WIDTHS),
            _PROC_WIDTHS,
        ),
    ]
    for gpu in gpus:
        for cells in _iter_proc_rows(gpu, verbose):
            out.append(row(cells, _PROC_WIDTHS))
    out.extend([hrule(_FRAME_WIDTH), "\n"])
    return "".join(out)
