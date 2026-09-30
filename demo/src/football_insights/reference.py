"""Hand-reviewed reference data: tournament classes, eras, crosswalk, lineage.

These YAML files hold names, codes, and definitions only, never match records
or indicator values, so they are committed and packaged into the images.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from itertools import pairwise
from pathlib import Path
from typing import Any

import yaml

REFERENCE_DIR = Path(__file__).parent / "reference"
FILES = ("tournaments.yaml", "eras.yaml", "crosswalk.yaml", "lineage.yaml")


class ReferenceError(ValueError):
    """A reference file is malformed or inconsistent."""


@dataclass(frozen=True)
class Category:
    name: str
    k: int
    competitive: bool
    friendly_like: bool
    label: str


@dataclass(frozen=True)
class Era:
    id: str
    start: int
    end: int
    label: str
    min_matches: int
    note: str


@dataclass(frozen=True)
class Mapping:
    team: str
    wdi: str | None
    match: str
    valid_from: int | None
    reason: str | None
    note: str | None

    def code_for_year(self, year: int) -> str | None:
        if not self.wdi:
            return None
        if self.valid_from is not None and year < self.valid_from:
            return None
        return self.wdi


@dataclass(frozen=True)
class Reference:
    categories: dict[str, Category]
    tournament_category: dict[str, str]
    major_tournaments: tuple[str, ...]
    eras: tuple[Era, ...]
    crosswalk: dict[str, Mapping]
    venue_aliases: dict[str, str]
    successions: tuple[dict[str, Any], ...]
    post_soviet_states: tuple[str, ...]
    digest: str

    def era_for_year(self, year: int) -> Era:
        for era in self.eras:
            if era.start <= year <= era.end:
                return era
        raise ReferenceError(f"no era covers {year}")

    def category_of(self, tournament: str) -> Category:
        try:
            return self.categories[self.tournament_category[tournament]]
        except KeyError as exc:
            raise ReferenceError(f"tournament not classified in tournaments.yaml: {tournament!r}") from exc


def _read(name: str, directory: Path) -> Any:
    with (directory / name).open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load(directory: Path = REFERENCE_DIR) -> Reference:
    digest = hashlib.sha256()
    for name in FILES:
        digest.update(name.encode())
        digest.update((directory / name).read_bytes())

    tournaments = _read("tournaments.yaml", directory)
    categories = {
        name: Category(name=name, k=int(v["k"]), competitive=bool(v["competitive"]),
                       friendly_like=bool(v["friendly_like"]), label=str(v["label"]))
        for name, v in tournaments["categories"].items()
    }
    tournament_category: dict[str, str] = {}
    for category, names in tournaments["tournaments"].items():
        if category not in categories:
            raise ReferenceError(f"unknown category {category!r} in tournaments.yaml")
        for tournament in names:
            if tournament in tournament_category:
                raise ReferenceError(f"tournament classified twice: {tournament!r}")
            tournament_category[tournament] = category
    majors = tuple(tournaments["major_tournaments"])
    for major in majors:
        if major not in tournament_category:
            raise ReferenceError(f"major tournament not classified: {major!r}")

    eras = tuple(
        Era(id=e["id"], start=int(e["start"]), end=int(e["end"]), label=str(e["label"]),
            min_matches=int(e["min_matches"]), note=str(e.get("note", "")))
        for e in _read("eras.yaml", directory)["eras"]
    )
    for before, after in pairwise(eras):
        if before.end + 1 != after.start:
            raise ReferenceError(f"eras are not contiguous: {before.label} then {after.label}")

    crosswalk: dict[str, Mapping] = {}
    for entry in _read("crosswalk.yaml", directory)["teams"]:
        team = str(entry["team"])
        if team in crosswalk:
            raise ReferenceError(f"team listed twice in crosswalk.yaml: {team!r}")
        crosswalk[team] = Mapping(
            team=team,
            wdi=entry.get("wdi"),
            match=str(entry["match"]),
            valid_from=entry.get("valid_from"),
            reason=entry.get("reason"),
            note=entry.get("note"),
        )

    lineage = _read("lineage.yaml", directory)
    return Reference(
        categories=categories,
        tournament_category=tournament_category,
        major_tournaments=majors,
        eras=eras,
        crosswalk=crosswalk,
        venue_aliases={str(a["venue"]): str(a["team"]) for a in lineage["venue_aliases"]},
        successions=tuple(lineage["successions"]),
        post_soviet_states=tuple(lineage["post_soviet_states"]),
        digest=digest.hexdigest(),
    )


@lru_cache(maxsize=1)
def get_reference() -> Reference:
    return load()
