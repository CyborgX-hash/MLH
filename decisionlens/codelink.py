"""Decision-to-code linking that survives renames.

A decision is linked to code by symbol and by file. Because files move, `RenameMap` replays the
repository history with rename detection (`git log -M --name-status`) so an old path recorded in
a decision can always be resolved to where that file lives today.
"""
from __future__ import annotations

import re
import subprocess
from typing import Dict, List, Optional, Set

from decisionlens.models import CodeRef, Decision

BACKTICK = re.compile(r"`([^`\n]{2,80})`")
PATH = re.compile(r"(?<![\w/.-])((?:[\w.-]+/)*[\w.-]+\.(?:py|c|h|cc|cpp|rs|go|js|ts|java|rb|toml|cfg))\b")
IDENT = re.compile(
    r"\b(?:[A-Za-z_]\w*\.[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*|[A-Za-z]+_[A-Za-z0-9_]+|[a-z]+[A-Z]\w+|Py[A-Z]\w+|_Py\w+)\b"
)
DEFINITION = re.compile(r"^\s*(?:async\s+def|def|class|fn|func|function|struct|enum|trait|#define|typedef)\b")


def _git(repo: str, *args: str) -> str:
    res = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if res.returncode not in (0, 1):
        raise RuntimeError(f"git {' '.join(args)} failed: {res.stderr.strip()}")
    return res.stdout


def head_commit(repo: str) -> str:
    return _git(repo, "rev-parse", "--short", "HEAD").strip()


def candidate_symbols(text: str) -> List[str]:
    found: List[str] = []
    for m in BACKTICK.finditer(text):
        tok = m.group(1).strip().rstrip("()")
        if re.fullmatch(r"[\w.]+", tok) and len(tok) > 2:
            found.append(tok)
    for m in IDENT.finditer(text):
        found.append(m.group(0))
    seen: Set[str] = set()
    out = []
    for s in found:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def candidate_paths(text: str) -> List[str]:
    return list(dict.fromkeys(m.group(1) for m in PATH.finditer(text)))


class RenameMap:
    """Maps any historical path to its current location (or None if deleted)."""

    def __init__(self) -> None:
        self.moved: Dict[str, Optional[str]] = {}

    @classmethod
    def build(cls, repo: str) -> "RenameMap":
        rm = cls()
        out = _git(repo, "log", "--name-status", "-M", "--reverse", "--format=%x00%H")
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) == 3 and parts[0].startswith("R"):
                old, new = parts[1], parts[2]
                rm.moved[old] = new
            elif len(parts) == 2 and parts[0] == "D":
                rm.moved[parts[1]] = None
            elif len(parts) == 2 and parts[0] in ("A", "M"):
                rm.moved.pop(parts[1], None) if parts[0] == "A" else None
        return rm

    def current(self, path: str) -> Optional[str]:
        seen = set()
        while path in self.moved and path not in seen:
            seen.add(path)
            nxt = self.moved[path]
            if nxt is None:
                return None
            path = nxt
        return path


def tracked_files(repo: str) -> Set[str]:
    return set(_git(repo, "ls-files").splitlines())


def find_symbol(repo: str, symbol: str, limit: int = 3) -> List[CodeRef]:
    pattern = re.escape(symbol.split(".")[-1])
    out = _git(repo, "grep", "-n", "-I", "-w", "-E", pattern)
    commit = head_commit(repo)
    defs: List[CodeRef] = []
    mentions: List[CodeRef] = []
    for line in out.splitlines():
        try:
            path, lineno, content = line.split(":", 2)
        except ValueError:
            continue
        kind = "definition" if DEFINITION.match(content) and pattern in content else "mention"
        ref = CodeRef(path=path, symbol=symbol, line=int(lineno), kind=kind, commit=commit)
        (defs if kind == "definition" else mentions).append(ref)
    chosen = defs[:limit]
    if not chosen:
        seen_files: Set[str] = set()
        for m in mentions:
            if m.path not in seen_files:
                seen_files.add(m.path)
                chosen.append(m)
            if len(chosen) >= 1:
                break
    return chosen


def link_decisions(decisions: List[Decision], repo: str, max_refs: int = 6) -> List[Decision]:
    files = tracked_files(repo)
    commit = head_commit(repo)
    rename = RenameMap.build(repo)
    for d in decisions:
        text = d.search_text() + " " + " ".join(e.quote for e in d.evidence)
        refs: List[CodeRef] = []
        for p in candidate_paths(text):
            now = rename.current(p)
            if now and now in files:
                refs.append(CodeRef(path=now, kind="file", commit=commit))
            else:
                match = [f for f in files if f.endswith("/" + p)]
                if len(match) == 1:
                    refs.append(CodeRef(path=match[0], kind="file", commit=commit))
        for sym in candidate_symbols(text):
            if len(refs) >= max_refs:
                break
            refs.extend(find_symbol(repo, sym))
        uniq = {(r.path, r.symbol): r for r in refs}
        d.code_refs = list(uniq.values())[:max_refs]
    return decisions
