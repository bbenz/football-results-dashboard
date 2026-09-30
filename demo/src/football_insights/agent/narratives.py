"""Labeled cached narratives for the offline fallback tier.

`python -m football_insights capture-narratives` saves grounded live answers
during a rehearsal; with AI_NARRATIVE_MODE=cached (or when the live model is
unreachable) the app serves them with their generation time and deployment,
never as live output.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from ..schemas import Answer


def key(question: str) -> str:
    normalized = re.sub(r"\s+", " ", question.strip().lower())
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def load(cache_dir: Path, question: str) -> Answer | None:
    path = cache_dir / f"{key(question)}.json"
    if not path.is_file():
        return None
    return Answer.model_validate_json(path.read_text(encoding="utf-8"))


def save(cache_dir: Path, answer: Answer, generated_at: str) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    stored = answer.model_copy(update={"cached_at": generated_at})
    path = cache_dir / f"{key(answer.question)}.json"
    path.write_text(json.dumps(stored.model_dump(mode="json"), indent=2), encoding="utf-8")
    return path
