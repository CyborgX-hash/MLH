"""Small, deterministic text helpers used to check quotes and claim support."""
import re
from typing import List, Set

STOPWORDS = frozenset(
    """a an and are as at be been but by can could do does for from has have how i if in into is it its
    just me my of on or our so than that the their them then there these they this to us was we were what
    when which who will with would you your also about all any each other such only very""".split()
)

# Phrases that mark an authoritative outcome statement.
RESOLUTION_CUES = re.compile(
    r"\b(we(?:'ve| have)? decided|decision is|let'?s go with|we(?:'ll| will) (?:go with|use|adopt)|"
    r"(?:is|are) accepted|approved|agreed|final(?:ly)? (?:decision|call)|closing (?:this )?in favou?r of|"
    r"we(?:'re| are) going with|merging|lgtm)\b",
    re.I,
)
# Phrases that mark an objection: needed before an alternative may be called "rejected".
OBJECTION_CUES = re.compile(
    r"(-1\b|\b(?:don'?t|do not|shouldn'?t|should not|won'?t|will not|can'?t|cannot)\b|\bnot (?:a )?good\b|"
    r"\bagainst\b|\breject(?:ed|ing)?\b|\bobject(?:ion)?\b|\bproblem\b|\bconcern\b|\btoo (?:slow|complex|risky)\b|"
    r"\binstead of\b|\brather than\b|\bdrawback\b|\bdoes(?:n'?t| not) (?:scale|work|support)\b)",
    re.I,
)


def normalize(text: str) -> str:
    text = re.sub(r"[`*_>\"'“”‘’]", "", text or "")
    return re.sub(r"\s+", " ", text).strip().lower()


def tokens(text: str) -> Set[str]:
    # Keeps tech terms like c++, c#, node.js, but strips sentence punctuation at the edges.
    raw = (t.strip(".-") for t in re.findall(r"[a-z0-9_+#.-]+", (text or "").lower()))
    return {t for t in raw if len(t) > 1 and t not in STOPWORDS}


def sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text or "") if len(s.strip()) >= 3]


def overlap(claim: Set[str], other: Set[str]) -> float:
    return len(claim & other) / len(claim) if claim else 0.0
