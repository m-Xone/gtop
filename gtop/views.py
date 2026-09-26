"""Panel renderers: turn collector output into structured lines of segments."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from xml.etree.ElementTree import Element

from .collectors import process_cpu_percent, process_name
from .widgets import Line, ProgressBar, Segment, blank, hrule, plain, row

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

_FRAME_WIDTH_MAX = 96


def _frame_width(screen_width: int) -> int:
    """Width to use for horizontal rules: tracks the terminal, capped at 96."""
    return max(20, min(_FRAME_WIDTH_MAX, screen_width - 1))


def _unavailable(label: str, title_w: int = 16) -> Line:
    return (plain(f"{label[:title_w].ljust(title_w)} [data not available]"),)


# ---------------------------------------------------------------------------
# CPU panel
# ---------------------------------------------------------------------------


def _cpu_grid(n_cores: int) -> tuple[int, int]:
    """Return ``(columns, bar_length)`` sized for the number of cores."""
    if n_cores > 24:
        return 4, 12
    if n_cores > 16:
        return 3, 20
    return 2, 35


def render_cpu(usage: Sequence[float], fill_char: str, screen_width: int) -> list[Line]:
    if not usage:
        return []

    n_cols, bar_length = _cpu_grid(len(usage))
    width = _frame_width(screen_width)

    bars: list[Line] = [
        ProgressBar(
            title=f"CPU {i}",
            pct=pct / 100.0,
            title_w=6,
            fill_char=fill_char,
            bar_length=bar_length,
            unit="%",
        ).render()
        for i, pct in enumerate(usage)
    ]

    lines: list[Line] = [hrule(width)]
    for start in range(0, len(bars), n_cols):
        group = bars[start : start + n_cols]
        combined: list[Segment] = []
        for j, bar in enumerate(group):
            if j > 0:
                combined.append(plain(" "))
            combined.extend(bar)
        lines.append(tuple(combined))
    lines.append(blank())
    return lines


# ---------------------------------------------------------------------------
# GPU panel — one block per detected device
# ---------------------------------------------------------------------------

# nvidia-smi's XML schema has drifted across driver versions; power metrics
# may live in either ``<gpu_power_readings>`` or ``<power_readings>``.
_POWER_SECTIONS: tuple[tuple[str, str, str], ...] = (
    # (section_tag, draw_tag, limit_tag)
    ("gpu_power_readings", "power_draw", "current_power_limit"),
    ("power_readings", "power_draw", "power_limit"),
)


def _memory_bar(gpu: Element, fill_char: str) -> Line:
    try:
        mem = gpu.find("fb_memory_usage")
        total = int(mem.find("total").text.split()[0])
        used = int(mem.find("used").text.split()[0])
        reserved_elt = mem.find("reserved")
        reserved = int(reserved_elt.text.split()[0]) if reserved_elt is not None else 0
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


def _utilization_bar(gpu: Element, fill_char: str) -> Line:
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


def _power_bar(gpu: Element, fill_char: str) -> Line:
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


def _temperature_bar(gpu: Element, fill_char: str) -> Line:
    try:
        parts = gpu.find("temperature").find("gpu_temp").text.split()
        temp = int(parts[0])
        scale = parts[1]
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


def _fan_bar(gpu: Element, fill_char: str) -> Line:
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


def _text(node: Element | None, default: str = "N/A") -> str:
    """Return an element's text, or *default* when the node or text is missing.

    ElementTree yields ``None`` for absent nodes and for present-but-empty
    ones; without this, those would reach the screen as the literal "None".
    """
    if node is None or node.text is None:
        return default
    return node.text


def _gpu_header(gpu: Element) -> Line:
    gpu_id = _text(gpu.find("minor_number"), "?")
    name_elt = gpu.find("product_name")
    arch_elt = gpu.find("product_architecture")
    if name_elt is not None and name_elt.text:
        arch = f"({arch_elt.text})" if arch_elt is not None and arch_elt.text else ""
        return (plain(f"GPU {gpu_id}: {name_elt.text} {arch}"),)
    return (plain(f"GPU {gpu_id}"),)


def render_gpu(gpu_info: Element, fill_char: str, screen_width: int) -> list[Line]:
    width = _frame_width(screen_width)
    lines: list[Line] = []
    for gpu in gpu_info.findall(".//gpu"):
        lines.append(hrule(width))
        lines.append(_gpu_header(gpu))
        lines.append(_utilization_bar(gpu, fill_char))
        lines.append(_memory_bar(gpu, fill_char))
        lines.append(_power_bar(gpu, fill_char))
        lines.append(_temperature_bar(gpu, fill_char))
        lines.append(_fan_bar(gpu, fill_char))
        lines.append(hrule(width))
    return lines


# ---------------------------------------------------------------------------
# Process table
# ---------------------------------------------------------------------------

_NAME_WIDTH = 50
_PROC_WIDTHS: tuple[int, ...] = (6, 10, _NAME_WIDTH, 7, 11)
_PROC_HEADERS: tuple[str, ...] = (
    "GPU ID",
    "Process ID",
    "Name",
    "CPU %",
    "GPU Mem",
)


def _truncate_name(name: str) -> str:
    """Middle-ellipsize to keep the first 23 and tail portion of a long name."""
    if len(name) <= _NAME_WIDTH:
        return name
    return name[:23] + "..." + name[26:_NAME_WIDTH]


def _iter_proc_rows(gpu: Element, verbose: bool) -> Iterable[tuple[str, ...]]:
    gpu_id = _text(gpu.find("minor_number"), "?")
    mem = gpu.find("fb_memory_usage")

    reserved_elt = mem.find("reserved") if mem is not None else None
    if reserved_elt is not None:
        yield gpu_id, "N/A", "[reserved]", "N/A", _text(reserved_elt)

    for proc in gpu.findall("processes/process_info"):
        pid_txt = _text(proc.find("pid"), "")
        try:
            pid = int(pid_txt)
        except ValueError:
            continue

        cpu_pct = process_cpu_percent(pid)
        cpu_cell = "N/A" if cpu_pct is None else str(cpu_pct)

        name = (
            process_name(pid, verbose=True)
            if verbose
            else _text(proc.find("process_name"), "unavailable")
        )

        yield (
            gpu_id,
            pid_txt,
            _truncate_name(name),
            cpu_cell,
            _text(proc.find("used_memory")),
        )


def render_processes(gpu_info: Element, verbose: bool, screen_width: int) -> list[Line]:
    gpus = gpu_info.findall(".//gpu")
    if not any(gpu.findall("processes/process_info") for gpu in gpus):
        return [(plain("Process data unavailable"),)]

    width = _frame_width(screen_width)
    lines: list[Line] = [
        hrule(width),
        row(_PROC_HEADERS, _PROC_WIDTHS),
        row(tuple("\u2500" * w for w in _PROC_WIDTHS), _PROC_WIDTHS),
    ]
    for gpu in gpus:
        for cells in _iter_proc_rows(gpu, verbose):
            lines.append(row(cells, _PROC_WIDTHS))
    lines.append(hrule(width))
    return lines
