"""Cross-platform contributor identity resolution with confidence scores.

Signals (combined as a noisy-OR): shared email, explicit profile link or .mailmap entry, identical
handle, identical multi-word display name, and near-identical handles. Accounts are merged when the
combined pairwise confidence reaches MERGE_AT.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from itertools import combinations
from typing import Dict, List, Sequence, Tuple

MERGE_AT = 0.7
WEIGHTS = {"email": 1.0, "link": 0.95, "handle": 0.6, "name": 0.5, "similar_handle": 0.4}


@dataclass(frozen=True)
class Account:
    platform: str
    handle: str
    name: str = ""
    email: str = ""
    links: Tuple[str, ...] = ()  # "platform:handle" strings this account claims as its own

    @property
    def key(self) -> str:
        return f"{self.platform}:{self.handle.lower()}"


@dataclass
class Cluster:
    members: List[Account]
    confidence: float
    signals: List[str] = field(default_factory=list)


def _norm_handle(h: str) -> str:
    return re.sub(r"[^a-z0-9]", "", h.lower())


def _norm_name(n: str) -> str:
    return " ".join(re.sub(r"[^a-z ]", "", n.lower()).split())


def pair_signals(a: Account, b: Account) -> Dict[str, float]:
    sig: Dict[str, float] = {}
    if a.email and a.email.lower() == b.email.lower():
        sig["email"] = WEIGHTS["email"]
    if b.key in {l.lower() for l in a.links} or a.key in {l.lower() for l in b.links}:
        sig["link"] = WEIGHTS["link"]
    ha, hb = _norm_handle(a.handle), _norm_handle(b.handle)
    if ha and ha == hb:
        sig["handle"] = WEIGHTS["handle"]
    elif ha and hb and difflib.SequenceMatcher(None, ha, hb).ratio() >= 0.85:
        sig["similar_handle"] = WEIGHTS["similar_handle"]
    na, nb = _norm_name(a.name), _norm_name(b.name)
    if na and na == nb and len(na.split()) >= 2:
        sig["name"] = WEIGHTS["name"]
    return sig


def combine(sig: Dict[str, float]) -> float:
    p = 1.0
    for w in sig.values():
        p *= 1 - w
    return round(1 - p, 3)


def resolve(accounts: Sequence[Account]) -> List[Cluster]:
    parent = {a.key: a.key for a in accounts}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    edges: Dict[str, List[Tuple[float, Dict[str, float]]]] = {}
    for a, b in combinations(accounts, 2):
        if a.platform == b.platform and a.handle.lower() == b.handle.lower():
            continue
        sig = pair_signals(a, b)
        conf = combine(sig)
        if conf >= MERGE_AT:
            ra, rb = find(a.key), find(b.key)
            if ra != rb:
                parent[ra] = rb
            edges.setdefault(a.key, []).append((conf, sig))
            edges.setdefault(b.key, []).append((conf, sig))

    groups: Dict[str, List[Account]] = {}
    for a in accounts:
        groups.setdefault(find(a.key), []).append(a)
    clusters = []
    for members in groups.values():
        confs = [c for m in members for c, _ in edges.get(m.key, [])]
        names = sorted({s for m in members for _, sig in edges.get(m.key, []) for s in sig})
        clusters.append(Cluster(members, min(confs) if confs else 1.0, names))
    return sorted(clusters, key=lambda c: c.members[0].key)


def parse_mailmap(text: str) -> List[Account]:
    """Turn `Proper Name <proper@email> Other Name <other@email>` lines into linked accounts."""
    accounts = []
    pat = re.compile(r"^(?P<name>[^<]*)<(?P<proper>[^>]+)>(?:\s*(?P<other_name>[^<]*)<(?P<other>[^>]+)>)?")
    for line in text.splitlines():
        m = pat.match(line.strip())
        if not m or line.lstrip().startswith("#"):
            continue
        name = m.group("name").strip()
        accounts.append(Account("git", m.group("proper").split("@")[0], name, m.group("proper")))
        if m.group("other"):
            accounts.append(
                Account("git", m.group("other").split("@")[0], m.group("other_name").strip() or name, m.group("proper"))
            )
    return accounts


def accounts_from_dicts(items: List[Dict]) -> List[Account]:
    return [
        Account(
            platform=i["platform"],
            handle=i["handle"],
            name=i.get("name", ""),
            email=i.get("email", ""),
            links=tuple(i.get("links", [])),
        )
        for i in items
    ]
