"""Extraction backends.

`OllamaBackend` is the real pipeline: an open-weight model served locally by Ollama.
`HeuristicBackend` is a deterministic, rule-based fallback used for offline CI runs and
unit tests. It makes no model claims and is reported as "heuristic" in every output.
"""
from __future__ import annotations

import json
import re
import urllib.request
from typing import Any, Dict, List, Protocol

from decisionlens.models import Post
from decisionlens.text import sentences

CANDIDATE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "idea": {"type": "string"},
                    "stance": {"type": "string", "enum": ["accepted", "rejected", "deferred", "open"]},
                    "summary": {"type": "string"},
                    "post_id": {"type": "integer"},
                    "quote": {"type": "string"},
                    "reasons": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["idea", "stance", "post_id", "quote", "reasons"],
            },
        }
    },
    "required": ["candidates"],
}

SYSTEM_PROMPT = """You analyse a technical discussion from an open-source project and extract the \
engineering decisions in it. Report each concrete technical approach, design or proposal that \
participants actually discuss. For each one give:
- idea: a short name for the approach (max 12 words)
- stance: "rejected" if participants argued against it or the maintainers declined it, "accepted" \
if it was adopted or agreed on, "deferred" if postponed to later, "open" if unresolved
- summary: one sentence describing the approach
- post_id: the number of the post that most clearly states the stance
- quote: an exact sentence copied word for word from that post that shows the stance
- reasons: why it was accepted or rejected, each reason in your own short words, \
taken from the posts only

Ignore greetings, thanks, meta-discussion and off-topic chatter. Never invent facts that are not \
in the posts. If the posts contain no decisions, return an empty list."""


class Backend(Protocol):
    name: str

    def extract(self, posts: List[Post], title: str) -> List[Dict[str, Any]]: ...


def format_posts(posts: List[Post], max_post_chars: int = 2500) -> str:
    out = []
    for p in posts:
        body = p.text if len(p.text) <= max_post_chars else p.text[:max_post_chars] + " [...]"
        out.append(f"[post {p.post_id} by @{p.author}]\n{body}")
    return "\n\n".join(out)


class OllamaBackend:
    def __init__(self, model: str = "gemma3:1b", host: str = "http://localhost:11434", timeout: int = 600):
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.name = f"ollama:{model}"

    def _chat(self, messages: List[Dict[str, str]]) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": CANDIDATE_SCHEMA,
            "options": {"temperature": 0, "num_ctx": 8192},
        }
        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))["message"]["content"]

    def extract(self, posts: List[Post], title: str) -> List[Dict[str, Any]]:
        user = f"Discussion title: {title}\n\n{format_posts(posts)}\n\nReturn the JSON object."
        raw = self._chat([{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}])
        return parse_candidates(raw)


def parse_candidates(raw: str) -> List[Dict[str, Any]]:
    """Tolerant JSON parsing: small models sometimes wrap or truncate their output."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []
    items = data.get("candidates", []) if isinstance(data, dict) else data
    out = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict) or not it.get("idea"):
            continue
        reasons = it.get("reasons") or []
        if isinstance(reasons, str):
            reasons = [reasons]
        try:
            post_id = int(it.get("post_id", 0))
        except (TypeError, ValueError):
            post_id = 0
        out.append(
            {
                "idea": str(it["idea"]).strip(),
                "stance": str(it.get("stance", "open")).lower().strip(),
                "summary": str(it.get("summary", "")).strip(),
                "post_id": post_id,
                "quote": str(it.get("quote", "")).strip(),
                "reasons": [str(r).strip() for r in reasons if str(r).strip()],
            }
        )
    return out


REJECT = re.compile(
    r"(\-1\b|\bi (?:would |do )?(?:strongly )?(?:oppose|object)|\bi (?:don'?t|do not) (?:think|like|want)|"
    r"\bnot (?:a )?(?:good|great) (?:idea|approach)|\bshould(?:n'?t| not)\b|\bbad idea\b|"
    r"\b(?:won'?t|will not|doesn'?t|does not) work\b|\brejected?\b|\bagainst (?:this|it|that)\b|"
    r"\btoo (?:complex|slow|risky|invasive|fragile)\b|\bwould break\b)",
    re.I,
)
ACCEPT = re.compile(
    r"(\+1\b|\bi (?:really )?like (?:this|that|the)\b|\bmakes sense\b|\bwe (?:decided|agreed)\b|"
    r"\b(?:accepted|approved)\b|\bsounds good\b|\blet'?s go with\b|\bi(?:'ll| will) (?:go with|support))",
    re.I,
)
DEFER = re.compile(r"\b(?:out of scope|postpone|defer(?:red)?|in a future (?:pep|pr|release|version)|later)\b", re.I)
DROPPED = re.compile(
    r"(?:\band\s+|\bbut\s+)?(?:\bdrop|\bremove|\babandon|\binstead of|\brather than)\s+(?:the\s+)?(?P<dropped>[^.;]+)", re.I
)
BECAUSE = re.compile(r"\b(?:because|since|due to|as it|as this|otherwise|which means)\b(.+)", re.I)


class HeuristicBackend:
    """Cue-phrase extractor. Deterministic; no model involved."""

    name = "heuristic"

    def extract(self, posts: List[Post], title: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for p in posts:
            sents = sentences(p.text)
            for i, s in enumerate(sents):
                stance = None
                if REJECT.search(s):
                    stance = "rejected"
                elif ACCEPT.search(s):
                    stance = "accepted"
                elif DEFER.search(s):
                    stance = "deferred"
                if not stance:
                    continue
                reasons = []
                m = BECAUSE.search(s)
                if m:
                    reasons.append(m.group(0).strip())
                elif i + 1 < len(sents) and BECAUSE.search(sents[i + 1]):
                    reasons.append(sents[i + 1])
                dropped = DROPPED.search(s)
                if dropped:
                    out.append(
                        {
                            "idea": dropped.group("dropped").strip(" .,;")[:100],
                            "stance": "rejected",
                            "summary": s,
                            "post_id": p.post_id,
                            "quote": s,
                            "reasons": reasons,
                        }
                    )
                    s_main = s[: dropped.start()]
                else:
                    s_main = s
                idea = BECAUSE.split(s_main)[0]
                idea = REJECT.sub("", idea) if stance == "rejected" else ACCEPT.sub("", idea)
                idea = re.sub(r"\b(?:is|are|would be) (?:a )?(?:good|great)(?: idea| approach)?\b", "", idea)
                idea = re.sub(r"\s+", " ", re.sub(r"^\W+|\W+$", "", idea)) or s
                out.append(
                    {
                        "idea": idea[:100],
                        "stance": stance,
                        "summary": s,
                        "post_id": p.post_id,
                        "quote": s,
                        "reasons": reasons,
                    }
                )
        return out


def make_backend(name: str, model: str = "gemma3:1b", host: str = "http://localhost:11434") -> Backend:
    if name == "ollama":
        return OllamaBackend(model=model, host=host)
    if name == "heuristic":
        return HeuristicBackend()
    raise ValueError(f"unknown backend: {name}")
