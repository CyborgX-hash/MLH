# DeciTrace

**Don't just understand what the code does. Understand why it was built that way.**

> Hackathon submission for **Problem 06: Open Source Decision Intelligence and Knowledge Recovery**, by team
> **Commit Crimes** (Mihika Mathur, Saksham Sontakke). MIT licensed. Open-weight models only.

DeciTrace connects to a public GitHub repository, collects its issues, pull requests, reviews, discussions,
commits and key files, and recovers the technical decisions buried in them. For each decision it records the
alternatives that were considered, the reasons given, who said what, and links to the original comments. It then
shows where the decision was implemented and warns reviewers when a new pull request touches that history.

## The problem

Engineering decisions in open-source projects are made in issue threads, review comments and discussions, and
then disappear once the thread closes. New contributors re-propose ideas that were already rejected, change code
without knowing why it is shaped that way, and the reasoning leaves with the people who wrote it. Formal records
such as PEPs and RFCs cover only the largest decisions.

## The solution, and what makes it different

| | GitHub search | AI summary | **DeciTrace** |
|---|---|---|---|
| Finds discussions by keyword | yes | – | yes (hybrid full-text + vector search) |
| States what was decided and what was rejected | no | yes, unverified | yes, **only when real comments support it** |
| Every claim links to the original comment | – | rarely | **always; fabricated or mismatched citations are refused** |
| Keeps disagreements unresolved instead of picking a winner | – | no | **yes; only a GitHub-verified maintainer can resolve** |
| Connects decisions to the PRs, commits and files that implemented them | no | no | yes, following renames and deletions |
| Warns when a new PR touches a historical decision | no | no | yes, as a review prompt that never blocks |

The AI model only *proposes*. A deterministic validator checks every citation against the stored GitHub
record (does it exist, is it in this repository, is the quote really there, does it support the claim, did an
owner/member/collaborator actually state the outcome without negating it) before anything is recorded.

## Features

- **Repository connection and ingestion:** URL validation, background sync with per-stage progress, pagination,
  rate-limit handling, incremental updates, upserts, safe file selection (no cloning, no binaries).
- **AI decision extraction:** an open-weight model reads the most-discussed threads and proposes decisions,
  alternatives, reasoning and each participant's position.
- **Evidence validation:** verified / partially verified / unsupported citations; explicit vs inferred vs
  unresolved status; rejected only with a recorded objection; unsupported candidates are refused.
- **Conflict handling and human review:** competing positions are kept; reviewers prove identity and write
  access through GitHub; full audit history; decisions can be superseded.
- **Cross-source linking:** issues, PRs, discussions and commits connected by explicit references (verified) or
  shared files, terms and similarity (shown only as *possible*).
- **Decision-to-code mapping:** implementing PRs, commits and files, including renames and later changes.
- **Ask DeciTrace (RAG):** answers grounded in retrieved evidence with GitHub citations, conflict warnings and an
  honest "no evidence" answer.
- **Timeline and graph** of each decision, built only from relationships the backend established.
- **PR impact analysis:** paste a PR URL to see which historical decisions it may affect and why.
- **PEP evaluation engine** (`decisionlens/`): blind recovery of rejected ideas from discuss.python.org threads,
  scored against each PEP's "Rejected Ideas" section.

## Screenshots

| Dashboard | Decision detail and timeline |
|---|---|
| ![Repository dashboard with sync progress](docs/screenshots/dashboard.jpg) | ![Decision detail with timeline](docs/screenshots/decision-timeline.jpg) |
| **Decision graph** | **Conflict review** |
| ![Decision graph](docs/screenshots/decision-graph.jpg) | ![Conflict review](docs/screenshots/conflict-review.jpg) |

All screenshots show real data from the public [`psf/requests`](https://github.com/psf/requests) repository.

## Architecture

```
            GitHub REST + GraphQL (read-only)
                          │
                ┌─────────▼──────────┐      issues, PRs, reviews, comments, discussions, commits, files
                │  Ingestion worker  │────────────────────────────────────────────────┐
                └─────────┬──────────┘                                                ▼
                          │                                                 PostgreSQL + pgvector
      ┌───────────────────┼────────────────────────┐                                  ▲
      ▼                   ▼                        ▼                                  │
 Link detector     Knowledge index          AI extraction (open-weight model)          │
 (verified /       (full-text + embeddings) proposes candidates ──► Evidence validator ─┘
  possible links)         │                                         (decides status, refuses
      │                   ▼                                          unsupported claims)
      └──► Code map ◄── Decisions ──► Hybrid retrieval ──► Grounded answer (cites only real sources)
                           │
             Human review (GitHub-verified write access) · Timeline · Graph · PR impact
```

| Layer | Technology |
|---|---|
| Frontend | React 19, Vite, TypeScript, Tailwind CSS 4, React Router, React Flow |
| Backend | Python, FastAPI, Pydantic, SQLAlchemy 2, Alembic, httpx |
| Database | PostgreSQL 16 with pgvector (Docker Compose) |
| Models | Any OpenAI-compatible endpoint; locally Ollama with open-weight models (see [HACKATHON.md](HACKATHON.md)) |
| Testing | pytest (166 backend tests against real PostgreSQL + 29 engine tests), oxlint, ruff, GitHub Actions |

Component details: [docs/TECHNICAL.md](docs/TECHNICAL.md). Security audit: [docs/AUDIT.md](docs/AUDIT.md).

## Installation

Requirements: Python 3.11+, Node 22+, Docker, and optionally [Ollama](https://ollama.com) for the models.

```bash
git clone https://github.com/CyborgX-hash/MLH.git decitrace && cd decitrace
cp .env.example .env
make setup      # backend virtualenv + frontend packages
make db         # PostgreSQL 16 + pgvector on localhost:5433
make migrate    # database schema
make backend    # API on http://localhost:8000 (docs at /docs)
make frontend   # web app on http://localhost:5173 (in a second terminal)
```

Models (pick what fits your machine; any OpenAI-compatible server works too):

```bash
ollama pull qwen2.5:1.5b                 # small: runs extraction and answers on an 8 GB laptop (low quality)
ollama pull qwen3:8b                     # default answer model, needs about 16 GB of RAM
ollama pull qwen3-embedding:0.6b         # enables vector search
```

Tests: `make test` (backend tests need the database from `make db`).

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://decitrace:decitrace@localhost:5433/decitrace` | PostgreSQL connection |
| `POSTGRES_USER` / `_PASSWORD` / `_DB` / `_PORT` | `decitrace` / `decitrace` / `decitrace` / `5433` | Docker Compose database |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | Allowed browser origins |
| `GITHUB_TOKEN` | empty | Optional. Raises GitHub's limit from 60 to 5,000 requests/hour and enables Discussions |
| `AI_PROVIDER`, `AI_BASE_URL` | `ollama`, `http://localhost:11434/v1` | OpenAI-compatible model endpoint |
| `AI_MODEL` | `qwen3:8b` | Answer model |
| `AI_EXTRACT_MODEL` | (`AI_MODEL`) | Extraction model, e.g. `qwen2.5:1.5b` on small machines |
| `AI_EMBED_MODEL` | `qwen3-embedding:0.6b` | Embeddings for vector search; empty = full-text only |
| `AI_API_KEY` | empty | Only for hosted providers |
| `AI_TIMEOUT` | `180` | Seconds per model call |
| `DECITRACE_ADMIN_TOKEN` | empty | Enables submitting decision candidates and index rebuilds over HTTP |
| `VITE_API_BASE_URL`, `VITE_BACKEND_PROXY_TARGET` | empty, `http://localhost:8000` | Frontend API location |

Secrets are only read on the server and never sent to the browser.

## Example workflow

1. **Connect** `https://github.com/psf/requests` on the Repositories page. A background sync collects issues,
   PRs, reviews, comments, commits and key files, links related records and builds the knowledge base.
2. **Extract decisions** from the dashboard. The model reads the most-discussed threads; the validator records
   only candidates whose cited comments check out.
3. **Explore** decisions by status, open one to see alternatives, reasoning, every participant's position with
   links to the original comments, the timeline, the graph and the implementing PRs and files.
4. **Review conflicts**: unresolved disagreements wait for a maintainer, who confirms an outcome with their own
   GitHub token.
5. **Ask** "Why was the current approach chosen?" and get an answer with numbered GitHub citations.
6. **Check a PR**: paste a pull request URL to see which decisions it may affect.

A recorded end-to-end example from real data is in [examples/](examples/README.md); the demo script is in
[docs/DEMO.md](docs/DEMO.md).

## Limitations

- **Extraction quality is limited by model size.** On our 8 GB machine only `qwen2.5:1.5b` fits next to the
  database. On five real `psf/requests` threads it proposed five candidates: three were refused by the validator,
  one was malformed, and one was recorded only as unresolved. The validator kept every wrong claim out, but a
  1.5B model does not find good decisions. Qwen3-8B (the configured default) has not completed a run on our
  hardware because it ran out of memory alongside Docker. The one well-formed decision in our examples was
  written by hand from real comments and then validated (it is labelled as such).
- **Rules are lexical.** Resolution and objection phrases are matched as words, so real decisions phrased
  unusually can stay "unresolved" until a human reviews them, and PR-impact signals can miss reworded conflicts.
- **Sampling without a token.** Without `GITHUB_TOKEN`, GitHub allows 60 requests/hour; DeciTrace samples the most
  recent activity and skips Discussions.
- **No user accounts or rate limiting.** Keep the API on localhost (the default) or behind an authenticating proxy.
- Discussion replies are capped at 50 per comment; timelines and graphs are not paginated.

## Future improvements

- Larger open-weight models on a GPU host, and model-assisted (not model-decided) stance detection to reduce the
  lexical-rule misses.
- A GitHub App that posts PR impact findings as a *non-blocking* review comment when maintainers opt in.
- GitHub OAuth for reviewers instead of pasting a token; per-user rate limits.
- Cross-platform identity resolution from the engine wired into the platform (mailing lists, Discourse).
- Incremental re-extraction scheduled after each sync, and evaluation on more PEPs and RFCs.

## Repository layout

| Path | Contents |
|---|---|
| `backend/` | FastAPI app (`app/`), Alembic migrations, tests |
| `frontend/` | React app |
| `decisionlens/` | PEP evaluation engine (CLI) and its tests in `tests/` |
| `examples/` | Real inputs and outputs, clearly labelled |
| `docs/` | Technical reference, audit, demo script, screenshots |
| `.github/` | PR template and CI workflow |

## License

MIT, see [LICENSE](LICENSE).
