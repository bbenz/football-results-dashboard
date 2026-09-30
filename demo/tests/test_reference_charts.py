"""Reference data loads, is internally consistent, and charts render safely."""

from __future__ import annotations

from football_insights.charts import render
from football_insights.reference import FILES, REFERENCE_DIR, get_reference, load
from football_insights.schemas import Chart, Series


def test_reference_digest_ignores_line_endings_and_comments(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # The curated version hashes this digest, so it must not depend on how a checkout stores line endings.
    for name in FILES:
        text = (REFERENCE_DIR / name).read_text(encoding="utf-8")
        (tmp_path / name).write_bytes(("# a comment\n" + text).replace("\n", "\r\n").encode("utf-8"))
    assert load(tmp_path).digest == get_reference().digest


def test_reference_files_are_consistent() -> None:
    ref = get_reference()
    assert len(ref.tournament_category) == 202
    assert ref.categories["friendly"].friendly_like and not ref.categories["world_cup"].friendly_like
    assert all(m in ref.tournament_category for m in ref.major_tournaments)
    assert ref.era_for_year(1872).id == "early" and ref.era_for_year(2026).id == "current"
    assert len(ref.crosswalk) == 337
    assert ref.crosswalk["Russia"].code_for_year(1991) is None
    assert ref.crosswalk["Russia"].code_for_year(1992) == "RUS"
    assert ref.crosswalk["England"].match == "shared"
    assert ref.venue_aliases["Yemen AR"] == "Yemen"


def test_chart_escapes_labels_and_uses_palette() -> None:
    chart = Chart(kind="line", title="<b>t</b>", x=["a&b", "c"], summary="s",
                  series=[Series(name="<script>", values=[1, None]), Series(name="two", values=[2, 3],
                                                                             lower=[1, 2], upper=[3, 4])])
    svg = render(chart)
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert "<script>" not in svg and "&lt;script&gt;" in svg
    assert "a&amp;b" in svg
    assert "#56B4E9" in svg and "#E69F00" in svg
    assert "stroke-dasharray" in svg


def test_hbar_chart() -> None:
    chart = Chart(kind="hbar", title="Top", x=["Avalon", "Borealis"], summary="s",
                  series=[Series(name="Rating", values=[2100.5, 1990.0])])
    svg = render(chart)
    assert "Avalon" in svg and "2,100" in svg


def test_axis_crossing_zero_never_shows_negative_zero() -> None:
    chart = Chart(kind="bar", title="Hosts", x=["Avalon", "Borealis", "Cascadia"], summary="s",
                  series=[Series(name="This edition", values=[-0.11, 0.16, 0.11]),
                          Series(name="Other editions", values=[-0.27, -0.14, -0.09])])
    svg = render(chart)
    assert ">-0<" not in svg and ">0<" in svg
