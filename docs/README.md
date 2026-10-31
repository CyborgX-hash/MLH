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
| M4 | Linker and threading | |
| M5 | Extractor through an OpenAI-compatible client | |
| M6 | Validator and status rules | |
| M7 | Code linking with renames | |
| M8 | Embeddings and grounded `/ask` | |
| M9 | PR check | |
| M10 | UI: intake, decisions, ask, PR check, review queue | |
| M11 | PEP blind evaluation report, final examples | |
