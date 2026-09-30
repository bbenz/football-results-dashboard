"""Operator scripts stay coherent: one definition per function, the same commands in PowerShell and bash,
and no mis-encoded characters in any tracked text file."""

from __future__ import annotations

import re
import subprocess
from collections import Counter

from conftest import REPO_ROOT

SCRIPTS = REPO_ROOT / "demo" / "scripts"


def duplicates(names: list[str]) -> list[str]:
    return sorted(name for name, count in Counter(names).items() if count > 1)


def test_powershell_functions_are_defined_once() -> None:
    for path in sorted(SCRIPTS.glob("*.ps1")):
        names = re.findall(r"^function\s+([\w-]+)", path.read_text(encoding="utf-8"), flags=re.MULTILINE)
        assert not duplicates(names), f"{path.name} redefines {duplicates(names)}"


def test_bash_functions_are_defined_once() -> None:
    for path in sorted(SCRIPTS.glob("*.sh")):
        names = re.findall(r"^([a-z_][a-z0-9_]*)\s*\(\)\s*\{", path.read_text(encoding="utf-8"), flags=re.MULTILINE)
        assert not duplicates(names), f"{path.name} redefines {duplicates(names)}"


def dispatcher_commands(text: str, pattern: str) -> set[str]:
    return {name for name in re.findall(pattern, text, flags=re.MULTILINE) if name not in ("default", "help", "*")}


def test_powershell_and_bash_offer_the_same_commands() -> None:
    ps = dispatcher_commands((SCRIPTS / "demo.ps1").read_text(encoding="utf-8"), r"^\s+'([a-z0-9-]+)'\s*\{")
    sh = dispatcher_commands((SCRIPTS / "demo.sh").read_text(encoding="utf-8"),
                             r"^\s+([a-z0-9][a-z0-9-]*(?:\|[a-z0-9-]+)*)\)")
    sh = {alias for entry in sh for alias in entry.split("|")} - {"help", "-h", "--help"}
    assert ps == sh, f"PowerShell only: {sorted(ps - sh)}; bash only: {sorted(sh - ps)}"


def test_no_mis_encoded_text_in_repository_files() -> None:
    # Tracked files plus new files that are not ignored, so a problem is caught before its first commit.
    listed = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                            cwd=REPO_ROOT, capture_output=True, check=True).stdout
    bad = []
    for name in filter(None, listed.decode("utf-8").split("\0")):
        path = REPO_ROOT / name
        if path.suffix.lower() in {".png", ".jpg", ".ico", ".woff", ".woff2"} or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "\u00e2\u20ac" in text or "\ufffd" in text:
            bad.append(name)
    assert not bad, f"mis-encoded characters (UTF-8 read as another code page) in {bad}"
