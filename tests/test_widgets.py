"""Widget primitives: segment structure, colors, and layout arithmetic."""

from __future__ import annotations

import dataclasses

import pytest

from gtop.widgets import (
    Color,
    ProgressBar,
    Segment,
    blank,
    colored,
    hrule,
    line_width,
    plain,
    row,
)


class TestSegments:
    def test_plain_is_default_colored(self):
        assert plain("abc") == Segment("abc", Color.DEFAULT)

    def test_colored_carries_its_color(self):
        assert colored("abc", Color.RED).color is Color.RED

    def test_line_width_sums_segments(self):
        line = (plain("ab"), colored("cde", Color.RED), plain(""))
        assert line_width(line) == 5

    def test_line_width_of_empty_line_is_zero(self):
        assert line_width(blank()) == 0


class TestHrule:
    def test_width_is_respected(self):
        assert line_width(hrule(42)) == 42

    def test_uses_box_drawing_character(self):
        assert hrule(3)[0].text == "─" * 3

    @pytest.mark.parametrize("width", [0, -1, -100])
    def test_non_positive_width_yields_empty_rule(self, width):
        assert hrule(width)[0].text == ""


class TestRow:
    def test_cells_are_ljust_with_two_space_gutters(self):
        # "a" padded to 3 + gutter, "b" padded to 4 + gutter == 11 columns.
        assert row(("a", "b"), (3, 4))[0].text == "a    b     "

    def test_width_is_sum_of_columns_and_gutters(self):
        assert line_width(row(("a", "b", "c"), (6, 10, 4))) == 6 + 10 + 4 + 6

    def test_extra_cells_without_widths_are_dropped(self):
        # zip() stops at the shorter sequence.
        assert row(("a", "b", "c"), (3,))[0].text == "a    "


class TestProgressBar:
    def test_returns_three_segments(self):
        segs = ProgressBar(title="t", pct=0.5, bar_length=20).render()
        assert len(segs) == 3

    def test_only_the_fill_segment_is_colored(self):
        head, fill, tail = ProgressBar(title="t", pct=0.5, bar_length=20).render()
        assert head.color is Color.DEFAULT
        assert tail.color is Color.DEFAULT
        assert fill.color is not Color.DEFAULT

    @pytest.mark.parametrize(
        ("pct", "expected"),
        [
            (0.0, Color.GREEN),
            (0.50, Color.GREEN),  # boundary: not strictly greater
            (0.51, Color.YELLOW),
            (0.90, Color.YELLOW),  # boundary
            (0.91, Color.RED),
            (1.0, Color.RED),
        ],
    )
    def test_default_thresholds(self, pct, expected):
        assert (
            ProgressBar(title="t", pct=pct, bar_length=20).render()[1].color is expected
        )

    def test_custom_thresholds(self):
        bar = ProgressBar(title="t", pct=0.65, bar_length=20, thresholds=(0.6, 0.7))
        assert bar.render()[1].color is Color.YELLOW

    @pytest.mark.parametrize("pct", [-5.0, -0.01, 1.5, 99.0])
    def test_out_of_range_percentages_are_clamped(self, pct):
        text = "".join(
            s.text for s in ProgressBar(title="t", pct=pct, bar_length=20).render()
        )
        assert ("0  " in text) or ("100" in text)

    def test_total_width_is_stable_across_percentages(self):
        widths = {
            line_width(ProgressBar(title="t", pct=p / 100, bar_length=30).render())
            for p in range(0, 101)
        }
        assert len(widths) == 1

    def test_percentage_is_embedded_in_the_fill_segment(self):
        fill = ProgressBar(title="t", pct=0.42, bar_length=40).render()[1]
        assert fill.text.endswith("42 ")

    def test_title_is_truncated_and_padded_to_title_w(self):
        head = ProgressBar(title="a-very-long-title", pct=0.1, title_w=6).render()[0]
        assert head.text.startswith("a-very ")

    def test_short_title_is_padded(self):
        head = ProgressBar(title="ab", pct=0.1, title_w=6).render()[0]
        assert head.text.startswith("ab     ")

    def test_epilogue_is_capped_at_20_chars(self):
        tail = ProgressBar(title="t", pct=0.1, epilogue="x" * 50).render()[2]
        assert tail.text.endswith("x" * 20)
        assert "x" * 21 not in tail.text

    def test_fill_char_uses_only_first_character(self):
        fill = ProgressBar(title="t", pct=1.0, bar_length=20, fill_char="ab").render()[
            1
        ]
        assert "b" not in fill.text

    def test_full_bar_reserves_room_for_the_percentage(self):
        fill = ProgressBar(title="t", pct=1.0, bar_length=20, fill_char="#").render()[1]
        assert fill.text == "#" * 17 + "100"

    def test_empty_bar_has_no_fill_characters(self):
        fill = ProgressBar(title="t", pct=0.0, bar_length=20, fill_char="#").render()[1]
        assert fill.text == "0  "

    def test_is_immutable(self):
        bar = ProgressBar(title="t", pct=0.5)
        with pytest.raises(dataclasses.FrozenInstanceError):
            bar.pct = 0.9  # type: ignore[misc]
