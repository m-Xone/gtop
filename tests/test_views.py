"""View layer: panel layout, schema tolerance, and process table assembly."""

from __future__ import annotations

import pytest

from gtop.views import (
    _cpu_grid,
    _frame_width,
    _truncate_name,
    render_cpu,
    render_gpu,
    render_processes,
)
from gtop.widgets import Color, line_width


def text_of(line) -> str:
    return "".join(seg.text for seg in line)


def all_text(lines) -> str:
    return "\n".join(text_of(line) for line in lines)


class TestFrameWidth:
    @pytest.mark.parametrize(
        ("screen", "expected"),
        [
            (200, 96),  # capped
            (120, 96),
            (97, 96),
            (80, 79),  # tracks terminal, leaving a column
            (40, 39),
            (10, 20),  # floor
            (1, 20),
        ],
    )
    def test_scales_with_screen_and_is_bounded(self, screen, expected):
        assert _frame_width(screen) == expected


class TestCpuGrid:
    @pytest.mark.parametrize(
        ("cores", "cols"),
        [(1, 2), (8, 2), (16, 2), (17, 3), (24, 3), (25, 4), (128, 4)],
    )
    def test_column_breakpoints(self, cores, cols):
        assert _cpu_grid(cores)[0] == cols

    def test_bar_shrinks_as_columns_grow(self):
        lengths = [_cpu_grid(n)[1] for n in (8, 20, 40)]
        assert lengths == sorted(lengths, reverse=True)


class TestRenderCpu:
    def test_no_usage_renders_nothing(self):
        assert render_cpu([], "|", 96) == []

    def test_one_line_per_row_plus_rule_and_spacer(self):
        # 8 cores at 2 columns = 4 bar rows, + 1 hrule + 1 blank.
        assert len(render_cpu([10.0] * 8, "|", 96)) == 6

    def test_odd_core_count_leaves_a_partial_final_row(self):
        # 5 cores at 2 columns = 3 rows (2, 2, 1).
        assert len(render_cpu([10.0] * 5, "|", 96)) == 5

    def test_each_core_is_labeled(self):
        text = all_text(render_cpu([10.0] * 4, "|", 96))
        for i in range(4):
            assert f"CPU {i}" in text

    def test_usage_is_scaled_from_percent_to_fraction(self):
        # 92% must land in the red band; if the /100 were dropped it would clamp.
        lines = render_cpu([92.0], "|", 96)
        colors = [s.color for s in lines[1] if s.color is not Color.DEFAULT]
        assert colors == [Color.RED]

    def test_low_usage_is_green(self):
        lines = render_cpu([5.0], "|", 96)
        assert [s.color for s in lines[1] if s.color is not Color.DEFAULT] == [
            Color.GREEN
        ]

    def test_rule_width_follows_screen(self):
        assert line_width(render_cpu([1.0], "|", 50)[0]) == 49


class TestRenderGpu:
    def test_emits_a_full_block_per_device(self, modern_gpu):
        # rule, header, util, mem, power, temp, fan, rule
        assert len(render_gpu(modern_gpu, "|", 96)) == 8

    def test_two_devices_produce_two_blocks(self, two_gpus):
        assert len(render_gpu(two_gpus, "|", 96)) == 16

    def test_header_includes_name_and_architecture(self, modern_gpu):
        assert "GPU 0: NVIDIA GeForce RTX 4080 (Ada Lovelace)" in all_text(
            render_gpu(modern_gpu, "|", 96)
        )

    def test_header_omits_architecture_when_absent(self, legacy_gpu):
        assert "GPU 0: Quadro NVS 5400M" in all_text(render_gpu(legacy_gpu, "|", 96))

    def test_header_falls_back_to_id_only(self, degenerate_gpu):
        assert "GPU 3" in all_text(render_gpu(degenerate_gpu, "|", 96))

    def test_memory_includes_reserved_in_the_total(self, modern_gpu):
        # 5120 used + 256 reserved
        assert "5376 MiB/16384 MiB" in all_text(render_gpu(modern_gpu, "|", 96))

    def test_memory_without_reserved_node(self, legacy_gpu):
        assert "512 MiB/2048 MiB" in all_text(render_gpu(legacy_gpu, "|", 96))

    def test_modern_power_section_is_read(self, modern_gpu):
        assert "180.25 W/320.0 W" in all_text(render_gpu(modern_gpu, "|", 96))

    def test_legacy_power_section_is_read(self, legacy_gpu):
        assert "15.0 W/45.0 W" in all_text(render_gpu(legacy_gpu, "|", 96))

    def test_fahrenheit_scale_is_supported(self, legacy_gpu):
        assert "140 F" in all_text(render_gpu(legacy_gpu, "|", 96))

    def test_celsius_scale_is_supported(self, modern_gpu):
        assert "62 C" in all_text(render_gpu(modern_gpu, "|", 96))

    @pytest.mark.parametrize(
        "label",
        ["Utilization", "Memory Usage", "Power Usage", "Temperature", "Fan Speed"],
    )
    def test_missing_metrics_degrade_to_a_placeholder(self, degenerate_gpu, label):
        text = all_text(render_gpu(degenerate_gpu, "|", 96))
        assert f"{label}" in text
        assert text.count("[data not available]") == 5

    def test_na_fan_speed_is_not_rendered_as_a_bar(self, legacy_gpu):
        assert "Fan Speed" in all_text(render_gpu(legacy_gpu, "|", 96))
        assert "[data not available]" in all_text(render_gpu(legacy_gpu, "|", 96))

    def test_rules_track_screen_width(self, modern_gpu):
        lines = render_gpu(modern_gpu, "|", 60)
        assert line_width(lines[0]) == 59
        assert line_width(lines[-1]) == 59


class TestTruncateName:
    def test_short_names_pass_through(self):
        assert _truncate_name("short") == "short"

    def test_exactly_at_limit_is_untouched(self):
        name = "x" * 50
        assert _truncate_name(name) == name

    def test_long_names_are_middle_ellipsized_to_the_limit(self):
        result = _truncate_name("y" * 200)
        assert len(result) == 50
        assert "..." in result

    def test_elision_keeps_the_head_then_a_middle_slice(self):
        """Documents the original (odd) truncation, preserved deliberately.

        The "..." marker elides only characters 23-26; the result is then
        hard-truncated at 50, so the real tail of a long name is dropped
        with no marker. Kept as-is to avoid changing on-screen output.
        """
        name = "a" * 60 + "TAIL"
        result = _truncate_name(name)
        assert result == name[:23] + "..." + name[26:50]
        assert len(result) == 50
        assert "TAIL" not in result


class TestRenderProcesses:
    def test_reports_unavailable_when_no_device_has_processes(self, no_process_gpu):
        lines = render_processes(no_process_gpu, False, 96)
        assert all_text(lines) == "Process data unavailable"

    def test_header_row_is_present(self, modern_gpu):
        assert "GPU ID" in all_text(render_processes(modern_gpu, False, 96))

    def test_non_verbose_uses_the_xml_process_name(self, modern_gpu):
        assert "/usr/bin/python3" in all_text(render_processes(modern_gpu, False, 96))

    def test_reserved_memory_gets_its_own_row(self, modern_gpu):
        text = all_text(render_processes(modern_gpu, False, 96))
        assert "[reserved]" in text
        assert "256 MiB" in text

    def test_no_reserved_row_when_the_node_is_absent(self, legacy_gpu):
        assert "[reserved]" not in all_text(render_processes(legacy_gpu, False, 96))

    def test_processes_on_later_devices_survive_an_empty_first_device(self, two_gpus):
        """Regression: an early return used to discard every device's rows."""
        text = all_text(render_processes(two_gpus, False, 96))
        assert "Process data unavailable" not in text
        assert "/opt/train.py" in text
        assert "4242" in text

    def test_column_alignment_is_uniform(self, modern_gpu):
        lines = render_processes(modern_gpu, False, 96)
        # Skip the enclosing rules; header, separator and data rows must match.
        body = lines[1:-1]
        assert len({line_width(line) for line in body}) == 1
