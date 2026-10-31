"""Grounded answer generation.

The model sees numbered sources [S1]..[Sn] and may cite only those IDs. It never writes URLs: the backend
maps cited IDs to the stored GitHub URLs, drops IDs that do not exist, strips any URL it invented, and
computes confidence itself. With no relevant evidence the model is not called at all.
"""
from __future__ import annotations

import re
from typing import List, Optional

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models import Repository
from app.services.ai.client import AIClient, ContextTooLong
from app.services.retrieval.indexer import index_decisions
from app.services.retrieval.search import Context, build_context, hybrid_search

NO_EVIDENCE = "No relevant evidence was found in this repository's ingested history, so DeciTrace cannot answer this."

SYSTEM_PROMPT = """You answer questions about the engineering history of the GitHub repository {repo}.
Rules:
- Use ONLY the numbered sources below. If they do not answer the question, set insufficient_evidence to true.
- Never invent decisions, people, dates, numbers or links. Do not write URLs; cite sources as [S1], [S2].
- Cite a source for every factual sentence.
- Separate facts from interpretation: write facts plainly; begin any interpretation with "This suggests".
- A decision marked "unresolved" or "no authoritative resolution" has NOT been decided: say it is unresolved,
  name the competing alternatives, and do not pick one.
- "inferred, not explicitly approved" means nobody with authority approved it in words: say so.
- If a rejection reason is "not recorded in the sources", say the reason is not recorded; do not guess one.
- If implementation says "No verified implementation evidence found", say no verified implementation exists.
- Say clearly when the evidence is incomplete.
Reply with a JSON object: {{"answer": "...", "citations": ["S1", ...], "insufficient_evidence": false}}"""


class AnswerDraft(BaseModel):
    answer: str = Field(..., max_length=6000)
    citations: List[str] = Field(default_factory=list)
    insufficient_evidence: bool = False


class Citation(BaseModel):
    id: str
    source_type: str
    source_number: Optional[int]
    url: Optional[str]
    title: str
    evidence: str
    author: Optional[str]


class Ask(BaseModel):
    answer: str
    citations: List[Citation]
    confidence: str  # supported | partial | insufficient
    insufficient_evidence: bool
    conflicts: List[dict] = Field(default_factory=list)
    decisions: List[dict] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    retrieval: dict = Field(default_factory=dict)
    model: Optional[str] = None


def _format(ctx: Context) -> str:
    parts = []
    for it in ctx.items:
        ref = it.source_type.replace("_", " ") + (f" #{it.number}" if it.number else "")
        parts.append(f"[{it.sid}] ({ref}{', author @' + it.author if it.author else ''}) {it.title}\n{it.text}")
    return "\n\n".join(parts)


def _insufficient(retrieval: dict, warnings: List[str], ctx: Optional[Context] = None, model: Optional[str] = None) -> Ask:
    return Ask(answer=NO_EVIDENCE, citations=[], confidence="insufficient", insufficient_evidence=True,
               warnings=warnings, retrieval=retrieval, decisions=ctx.decisions if ctx else [], model=model)


def answer_question(db: Session, repo: Repository, question: str, ai: AIClient) -> Ask:
    index_decisions(db, repo, ai)  # decisions change through reviews; keep their chunks current
    found = hybrid_search(db, repo.id, question, ai)
    retrieval = {"mode": found.mode, "hits": len(found.hits)}
    warnings = [found.note] if found.note else []
    if not found.hits:
        return _insufficient(retrieval, warnings)

    ctx = build_context(db, found)
    conflicts = [{"decision_id": d["id"], "topic": d["topic"], "alternatives": [a["name"] for a in d["alternatives"]]}
                 for d in ctx.decisions if d["status"] == "unresolved" and d["conflict_detected"]]

    messages = [{"role": "system", "content": SYSTEM_PROMPT.format(repo=repo.full_name)},
                {"role": "user", "content": f"Sources:\n{_format(ctx)}\n\nQuestion: {question}"}]
    try:
        draft = ai.chat_json(messages, AnswerDraft)
    except ContextTooLong:
        ctx = build_context(db, found, max_chars=4000)  # retry once with less context
        messages[1]["content"] = f"Sources:\n{_format(ctx)}\n\nQuestion: {question}"
        draft = ai.chat_json(messages, AnswerDraft)

    by_id = {it.sid: it for it in ctx.items}
    cited = list(dict.fromkeys([c for c in draft.citations if c in by_id] +
                               [m for m in re.findall(r"\[(S\d+)\]", draft.answer) if m in by_id]))
    unknown = sorted({m for m in re.findall(r"\[(S\d+)\]", draft.answer) + draft.citations if m not in by_id})
    text = re.sub(r"\[(S\d+)\]", lambda m: m.group(0) if m.group(1) in by_id else "", draft.answer)
    allowed_urls = {it.url for it in ctx.items if it.url}
    text, n_urls = re.subn(r"https?://\S+", lambda m: m.group(0) if m.group(0).rstrip(".,)") in allowed_urls else "[link removed]", text)
    if unknown:
        warnings.append(f"The model cited sources that were not retrieved ({', '.join(unknown)}); they were removed.")
    if "[link removed]" in text:
        warnings.append("The model wrote links that are not in the retrieved evidence; they were removed.")

    if draft.insufficient_evidence or not cited:
        if not cited and not draft.insufficient_evidence:
            warnings.append("The model's answer cited no retrieved evidence, so it was withheld.")
        return _insufficient(retrieval, warnings, ctx, ai.model)

    items = [by_id[c] for c in cited]
    if any(it.verified for it in items):
        confidence = "supported"
    else:
        confidence = "partial"
        warnings.append("No cited source is a verified, explicitly established decision; treat the answer as partial.")
    if conflicts:
        warnings.append("Some retrieved decisions are unresolved: participants disagreed and no authoritative "
                        "resolution exists.")
    return Ask(
        answer=text.strip(), confidence=confidence, insufficient_evidence=False, conflicts=conflicts,
        decisions=ctx.decisions, warnings=warnings, retrieval=retrieval, model=ai.model,
        citations=[Citation(id=it.sid, source_type=it.source_type, source_number=it.number, url=it.url,
                            title=it.title, evidence=it.text[:600], author=it.author) for it in items],
    )
