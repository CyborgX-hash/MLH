# DeciTrace architecture notes

DeciTrace recovers engineering decisions from public project history and keeps every claim traceable.

**Principle:** AI helps recover history; it never makes decisions. When developers disagree and no
authoritative resolution exists, the decision stays `unresolved` and is flagged for human review. An
alternative is `rejected` only with an explicit objection or decline; otherwise it is `considered_not_selected`.

## Data flow

```
repo URL → collectors (GitHub REST/GraphQL, Discourse) → messages (original text, URL, author, time)
        → linker (#refs, closes, PR↔commit↔files) → decision threads
        → LLM extraction (open-weight model, schema-constrained, must cite message IDs + quotes)
        → validator (quote verification, status rules, conflict → unresolved)
        → code links (PR, commit, files, symbols; rename-aware) → pgvector index
        → /ask (answers only from retrieved, verified evidence) and /pr-check
```

## Milestones

| # | Milestone | Status |
|---|---|---|
| M0 | Repo hygiene: PR template, CI, honest HACKATHON.md | done |
| M1 | Backend and frontend scaffold, Postgres + pgvector, health check | done |
| M2 | GitHub client and incremental ingestion (issues, PRs, reviews, discussions, commits, code) | done |
| M3 | Discourse collector + PEP mode (port from `decisionlens`) | |
| M4 | Cross-source linking (verified vs possible), decision deduplication | done |
| M5 | Extractor through an OpenAI-compatible client | |
| M6 | Evidence validator, status rules, conflict detection, authorised human review, audit history | done |
| M7 | Decision-to-code mapping with renames, deletions and later changes | done |
| M8 | Knowledge index (full-text + pgvector), hybrid retrieval, grounded `/ask` | done (Qwen3-8B not yet verified) |
| M9 | PR impact analysis (deterministic, never blocks) | done |
| M10b | Full technical and security audit, fixes ([AUDIT.md](AUDIT.md)) | done |
| M10 | UI: landing, connect, dashboard, explorer, decision detail (timeline + graph), ask, conflict review | done |
| M11 | PEP blind evaluation report, final examples | |
