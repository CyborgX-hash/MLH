"""Text utilities: HTML cleaning, tokenising, sentence splitting, chunking."""
from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Iterable, List, Set

from decisionlens.models import Post

STOPWORDS = frozenset(
    """a an and are as at be been but by can could do does for from has have how i if in into is it
    its just may me more most my no not of on one or our out over so some than that the their them
    then there these they this to up us was we were what when which who will with would you your
    also about all any each other such only very""".split()
)

_VOID = {"br", "img", "hr", "input", "meta", "link", "wbr"}
_BLOCK = {"p", "div", "li", "ul", "ol", "pre", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "br"}


class _Cooked(HTMLParser):
    """Turns Discourse 'cooked' HTML into plain text, dropping quoted replies."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: List[str] = []
        self.skip = 0
        self.stack: List[tuple] = []

    def handle_starttag(self, tag, attrs):
        if tag in _VOID:
            if tag == "br" and not self.skip:
                self.out.append("\n")
            return
        cls = (dict(attrs).get("class") or "").split()
        skip = (tag == "aside" and "quote" in cls) or (tag == "div" and "meta" in cls)
        self.stack.append((tag, skip))
        if skip:
            self.skip += 1
        elif tag in _BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                for _, was_skip in self.stack[i:]:
                    if was_skip:
                        self.skip -= 1
                del self.stack[i:]
                break
        if tag in _BLOCK and not self.skip:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def clean_html(cooked: str) -> str:
    parser = _Cooked()
    parser.feed(cooked or "")
    text = "".join(parser.out)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def tokens(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9_]+", text.lower()) if len(t) > 1 and t not in STOPWORDS]


def token_set(text: str) -> Set[str]:
    return set(tokens(text))


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[`*_\"'“”‘’]", "", text)).strip().lower()


def sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip() for p in parts if len(p.strip()) >= 8]


def overlap(claim: Set[str], other: Set[str]) -> float:
    """Fraction of the claim's tokens that appear in `other`."""
    return len(claim & other) / len(claim) if claim else 0.0


def jaccard(a: Set[str], b: Set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def cosine_sets(a: Set[str], b: Set[str]) -> float:
    return len(a & b) / ((len(a) * len(b)) ** 0.5) if a and b else 0.0


def chunk_posts(posts: Iterable[Post], max_chars: int = 6000, max_post_chars: int = 2500) -> List[List[Post]]:
    """Split a long thread into consecutive chunks that fit a model's context window."""
    chunks: List[List[Post]] = []
    cur: List[Post] = []
    size = 0
    for p in posts:
        n = min(len(p.text), max_post_chars) + 40
        if cur and size + n > max_chars:
            chunks.append(cur)
            cur, size = [], 0
        cur.append(p)
        size += n
    if cur:
        chunks.append(cur)
    return chunks
