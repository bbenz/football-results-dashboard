"""Documentation links: every relative link and #anchor in the repository resolves, as GitHub renders them."""

from __future__ import annotations

import importlib.util
import sys

from conftest import REPO_ROOT

spec = importlib.util.spec_from_file_location("check_links", REPO_ROOT / "demo" / "scripts" / "check_links.py")
links = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
sys.modules["check_links"] = links
spec.loader.exec_module(links)  # type: ignore[union-attr]


def test_repository_links_resolve() -> None:
    assert links.broken_links(links.markdown_files()) == []


def test_slugs_match_github_headings() -> None:
    assert links.slug("Identity: keyless everywhere") == "identity-keyless-everywhere"
    assert links.slug("Which should my hackathon team choose?") == "which-should-my-hackathon-team-choose"
    assert links.slug("Segment 9: Q&A (53:00–60:00)") == "segment-9-qa-53006000"
    assert links.slug("Question 8 (extension): What were the biggest upsets of each era?") == \
        "question-8-extension-what-were-the-biggest-upsets-of-each-era"


def test_broken_files_and_anchors_are_reported(tmp_path) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "other.md").write_text("# Real heading\n\n## Twice\n\n## Twice\n", encoding="utf-8")
    page = tmp_path / "page.md"
    page.write_text(
        "[ok](other.md#real-heading) [dup](other.md#twice-1) [web](https://example.com/missing)\n"
        "[missing file](nope.md) [missing anchor](other.md#nowhere)\n"
        "```\n[inside a code block](ignored.md)\n```\n",
        encoding="utf-8")
    problems = links.broken_links([page])
    assert len(problems) == 2
    assert "nope.md (no such file)" in problems[0]
    assert "other.md#nowhere (no heading with anchor #nowhere)" in problems[1]
