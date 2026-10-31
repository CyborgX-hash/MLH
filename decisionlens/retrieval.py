"""Semantic retrieval over decision records.

Dense embeddings from `sentence-transformers/all-MiniLM-L6-v2` (open weights) are used when the
optional `embeddings` extra is installed. Otherwise a pure-Python TF-IDF index is used, so the
tool still works, and CI stays fast, with zero heavy dependencies.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Dict, List, Sequence, Tuple

from decisionlens.models import Decision
from decisionlens.text import tokens

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class TfidfEmbedder:
    name = "tfidf"

    def __init__(self, corpus: Sequence[str]):
        df: Counter = Counter()
        for doc in corpus:
            df.update(set(tokens(doc)))
        n = max(len(corpus), 1)
        self.idf: Dict[str, float] = {t: math.log((1 + n) / (1 + c)) + 1 for t, c in df.items()}

    def embed(self, text: str) -> Dict[str, float]:
        tf = Counter(tokens(text))
        vec = {t: c * self.idf[t] for t, c in tf.items() if t in self.idf}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {t: v / norm for t, v in vec.items()}


class DenseEmbedder:
    name = EMBED_MODEL

    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer  # optional dependency

        self.model = SentenceTransformer(EMBED_MODEL)

    def embed(self, text: str) -> List[float]:
        return self.model.encode(text, normalize_embeddings=True).tolist()


def _cos(a, b) -> float:
    if isinstance(a, dict):
        return sum(v * b.get(t, 0.0) for t, v in a.items())
    return sum(x * y for x, y in zip(a, b))


class DecisionIndex:
    def __init__(self, decisions: List[Decision], prefer: str = "auto"):
        self.decisions = decisions
        corpus = [d.search_text() for d in decisions]
        self.embedder = None
        if prefer in ("auto", "dense"):
            try:
                self.embedder = DenseEmbedder()
            except Exception:
                if prefer == "dense":
                    raise
        if self.embedder is None:
            self.embedder = TfidfEmbedder(corpus)
        self.vectors = [self.embedder.embed(t) for t in corpus]

    @property
    def backend(self) -> str:
        return self.embedder.name

    def search(self, query: str, k: int = 5, status: str = "") -> List[Tuple[float, Decision]]:
        q = self.embedder.embed(query)
        scored = [
            (_cos(q, v), d)
            for v, d in zip(self.vectors, self.decisions)
            if not status or d.status == status
        ]
        scored.sort(key=lambda x: -x[0])
        return [(s, d) for s, d in scored[:k] if s > 0]
