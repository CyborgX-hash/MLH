"""Find explicit GitHub references in text. Only references to *this* repository are returned."""
import re
from dataclasses import dataclass
from typing import List, Optional

_N = r"(?P<num>\d{1,7})"
_QUAL = r"(?:(?P<owner>[A-Za-z0-9][\w.-]*)/(?P<repo>[\w.-]+))?"
HASH_REF = re.compile(rf"(?<![\w/&#]){_QUAL}#{_N}\b")
URL_REF = re.compile(
    r"https?://github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)/(?P<kind>issues|pull|discussions)/(?P<num>\d{1,7})\b", re.I
)
CLOSING = re.compile(rf"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b\s*:?\s+{_QUAL}#{_N}\b", re.I)
SUPERSEDES = re.compile(rf"\b(?:supersede[sd]?|replace[sd]?|obsolete[sd]?)\b\s+(?P<by>by\s+)?{_QUAL}#{_N}\b", re.I)
CONFLICTS = re.compile(rf"\b(?:conflicts?\s+with|contradicts|reverts?|revert\s+of)\b\s+{_QUAL}#{_N}\b", re.I)
REVERT_COMMIT = re.compile(r"\bThis reverts commit (?P<sha>[0-9a-f]{7,40})\b", re.I)
MERGE_PR = re.compile(r"^Merge pull request #(?P<num>\d{1,7})\b|\(#(?P<num2>\d{1,7})\)\s*$", re.M)
CODE = re.compile(r"```.*?```|`[^`\n]*`", re.S)
PATH = re.compile(r"(?<![\w/.-])((?:[\w.-]+/)*[\w.-]+\.(?:py|pyi|js|jsx|ts|tsx|go|rs|java|kt|rb|php|c|h|cc|cpp|hpp|cs|swift|sql|toml|cfg|ini|ya?ml|json|md|rst))\b")


@dataclass(frozen=True)
class Ref:
    number: int
    relation: str  # references | implements | supersedes | conflicts_with
    signal: str
    snippet: str
    reverse: bool = False  # True when the *target* is the subject ("superseded by #N")


def strip_code(text: str) -> str:
    """Code blocks hold examples and colour codes, not references."""
    return CODE.sub(" ", text or "")


def _same_repo(m: re.Match, owner: str, repo: str) -> bool:
    o, r = m.groupdict().get("owner"), m.groupdict().get("repo")
    return o is None or (o.lower() == owner.lower() and r.lower() == repo.lower())


def _snippet(text: str, m: re.Match, width: int = 80) -> str:
    start, end = max(m.start() - width, 0), min(m.end() + width, len(text))
    return " ".join(text[start:end].split())


def find_refs(text: str, owner: str, repo: str) -> List[Ref]:
    clean = strip_code(text)
    out: List[Ref] = []
    special = set()
    for pattern, relation, signal in (
        (CLOSING, "implements", "closing_keyword"),
        (SUPERSEDES, "supersedes", "explicit_reference"),
        (CONFLICTS, "conflicts_with", "explicit_reference"),
    ):
        for m in pattern.finditer(clean):
            if _same_repo(m, owner, repo):
                n = int(m.group("num"))
                reverse = relation == "supersedes" and bool(m.groupdict().get("by"))
                out.append(Ref(n, relation, signal, _snippet(clean, m), reverse))
                special.add(n)
    for m in HASH_REF.finditer(clean):
        n = int(m.group("num"))
        if n not in special and _same_repo(m, owner, repo):
            out.append(Ref(n, "references", "explicit_reference", _snippet(clean, m)))
    for m in URL_REF.finditer(clean):
        n = int(m.group("num"))
        if n not in special and _same_repo(m, owner, repo):
            out.append(Ref(n, "references", "explicit_reference", _snippet(clean, m)))
    return out


def pr_number_in_commit(message: str) -> Optional[int]:
    """Squash-merge "Title (#123)" or merge-commit "Merge pull request #123" conventions."""
    m = MERGE_PR.search((message or "").split("\n", 1)[0])
    if not m:
        return None
    return int(m.group("num") or m.group("num2"))


def reverted_sha(message: str) -> Optional[str]:
    m = REVERT_COMMIT.search(message or "")
    return m.group("sha").lower() if m else None


def mentioned_paths(text: str) -> List[str]:
    return list(dict.fromkeys(m.group(1) for m in PATH.finditer(text or "")))
