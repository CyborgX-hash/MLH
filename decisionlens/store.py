"""Knowledge storage: a JSON file of decision records with deterministic IDs."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from decisionlens import __version__
from decisionlens.models import Decision

SCHEMA_VERSION = 1


def save_decisions(path: str, decisions: List[Decision], meta: Dict[str, Any]) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "tool_version": __version__,
        "meta": meta,
        "decisions": [d.to_dict() for d in decisions],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)


def load_decisions(path: str) -> Tuple[List[Decision], Dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    return [Decision.from_dict(d) for d in payload["decisions"]], payload.get("meta", {})


def merge_stores(*groups: List[Decision]) -> List[Decision]:
    by_id: Dict[str, Decision] = {}
    for group in groups:
        for d in group:
            by_id[d.decision_id] = d
    return list(by_id.values())
