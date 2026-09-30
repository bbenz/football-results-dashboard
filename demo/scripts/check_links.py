"""Check that every relative link and #anchor in the repository's Markdown files resolves.

Anchors follow GitHub's heading slugs: lowercase, punctuation removed, spaces turned into hyphens, and
-1, -2, ... appended to repeated headings. External links are not fetched.

Usage: python demo/scripts/check_links.py   (exit code 1 lists every broken link)
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")


def slug(heading: str) -> str:
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading).lower()
    kept = "".join(ch for ch in text if ch in " -_" or unicodedata.category(ch)[0] in "LNM")
    return kept.replace(" ", "-")


def prose_lines(text: str) -> list[tuple[int, str]]:
    lines, fenced = [], False
    for number, line in enumerate(text.splitlines(), start=1):
        if FENCE.match(line):
            fenced = not fenced
        elif not fenced:
            lines.append((number, line))
    return lines


def anchors(path: Path) -> set[str]:
    found: set[str] = set()
    seen: dict[str, int] = {}
    for _, line in prose_lines(path.read_text(encoding="utf-8")):
        match = HEADING.match(line)
        if match:
            base = slug(match.group(2))
            count = seen.get(base, 0)
            seen[base] = count + 1
            found.add(base if count == 0 else f"{base}-{count}")
    return found


def markdown_files() -> list[Path]:
    git = shutil.which("git")
    if git is None:
        raise SystemExit("git is not on PATH")
    listed = subprocess.run([git, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "*.md"],
                            cwd=ROOT, capture_output=True, check=True).stdout.decode("utf-8")
    paths = [ROOT / name for name in listed.split("\0") if name]
    # The generation prompts are published only as the presenter decides; their README is ours to check.
    return sorted(p for p in paths if p.is_file() and (p.parent.name != "prompts" or p.name == "README.md"))


def broken_links(files: list[Path]) -> list[str]:
    problems = []
    cache: dict[Path, set[str]] = {}
    for path in files:
        for number, line in prose_lines(path.read_text(encoding="utf-8")):
            for target in LINK.findall(line):
                if re.match(r"^[a-z][a-z0-9+.-]*:", target, flags=re.IGNORECASE):
                    continue  # http:, https:, mailto: and other schemes
                file_part, _, anchor = target.partition("#")
                resolved = (path.parent / unquote(file_part)).resolve() if file_part else path
                where = f"{path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path}:{number}"
                if not resolved.exists():
                    problems.append(f"{where}: {target} (no such file)")
                elif anchor and resolved.suffix.lower() == ".md":
                    known = cache.setdefault(resolved, anchors(resolved))
                    if anchor.lower() not in known:
                        problems.append(f"{where}: {target} (no heading with anchor #{anchor})")
    return problems


def main() -> int:
    files = markdown_files()
    problems = broken_links(files)
    for problem in problems:
        print(problem)
    print(f"link check: {len(problems)} broken link(s) in {len(files)} Markdown files")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
