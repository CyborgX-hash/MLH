# DecisionLens: Open Source Decision Intelligence and Knowledge Recovery

> **Hackathon:** Problem 06, Open Source Decision Intelligence and Knowledge Recovery
> **Team:** Commit Crimes (Mihika Mathur, Saksham Sontakke)

Important engineering decisions in open-source projects are made in issue threads, PR reviews and
forums, then buried once the thread closes. New contributors re-propose ideas that were already
rejected, and nobody remembers why. DecisionLens reads a public discussion and recovers **what was
decided, which alternatives were rejected and why**, links each decision to the code it affects, and
shows the relevant history when a new pull request touches that code. Every claim cites the original
post, so a maintainer can verify it.

## How it works

```
Discourse thread ──► ingest ──► chunk ──► LLM extraction (map) ──► citation grounding ──► merge (reduce)
                                                                                              │
         PR diff ──► decision lookup ◄── code linking (symbols + rename-aware paths) ◄── decision store
```

| Stage | Module | What it does |
|---|---|---|
| Collect | `ingest.py` | Reads a public Discourse thread through its JSON API (read-only). Quoted replies and signatures are stripped. |
| Extract (map) | `llm.py`, `extract.py` | Splits long threads into context-sized chunks. An open-weight model served by **Ollama** returns candidate decisions as schema-constrained JSON: idea, stance (accepted, rejected, deferred, open), reasons, cited post and quote. |
| Verify | `extract.py` | **Claim-level grounding.** The quote and every reason must be found in a real post (verbatim, or a sentence with at least 60% token overlap). Anything unsupported is dropped, so hallucinated reasons do not reach the output. |
| Merge (reduce) | `extract.py` | The same idea mentioned in several chunks becomes one decision. The final stance is a vote that weights later posts more, because discussions converge. |
| Store | `store.py` | JSON records with deterministic IDs (`DEC-<hash of thread + idea>`), source URL, author and post number for every piece of evidence. |
| Retrieve | `retrieval.py` | Semantic search. Uses `sentence-transformers/all-MiniLM-L6-v2` when the `embeddings` extra is installed, and a pure-Python TF-IDF index otherwise. |
| Link to code | `codelink.py` | Finds symbols and file paths mentioned in a decision and locates their definitions with `git grep`. `RenameMap` replays history with `git log -M` so a path recorded years ago still resolves to where the file lives today. |
| PR intelligence | `pr.py` | Takes a diff or a list of changed files, finds linked decisions (file hit, symbol hit, semantic similarity) and prints a markdown summary with evidence links. **It never posts anything to a real project.** |
| Identity | `identity.py` | Resolves one contributor across GitHub, Discourse and mailing lists using shared email, explicit profile links, `.mailmap`, handles and names, with a confidence score. |
| Evaluate | `evaluate.py` | Blind test on Python PEPs: the model sees only the discussion; the PEP's "Rejected Ideas" section is the hidden answer key. |

## DeciTrace web platform (in progress)

The `decisionlens` package below is the working extraction engine. It is being grown into **DeciTrace**, a
web platform: FastAPI backend, React frontend, PostgreSQL with pgvector. Today the platform connects
public GitHub repositories and ingests their history; AI decision extraction arrives in later pull requests.

| Folder | Purpose |
|---|---|
| `backend/app/api/routes/` | FastAPI routers (`/api/health` today) |
| `backend/app/core/` | settings from environment variables (`config.py`) |
| `backend/app/db/` | SQLAlchemy engine, session and declarative base |
| `backend/app/models/`, `schemas/` | ORM tables and Pydantic request/response models |
| `backend/app/services/` | `github`, `extraction`, `evidence`, `retrieval`, `impact`: empty packages for the next milestones |
| `backend/app/workers/` | background ingestion and extraction jobs (next milestones) |
| `backend/alembic/` | database migrations (`0001` enables pgvector) |
| `frontend/src/` | `pages`, `layouts`, `components`, `hooks`, `services` (API client), `types`, `lib` |
| `docs/` | architecture notes |

Requirements: Python 3.11+, Node 22+, Docker.

```bash
cp .env.example .env
make setup        # backend venv + npm install
make db           # PostgreSQL 16 + pgvector on localhost:5433
make migrate      # alembic upgrade head
make backend      # http://localhost:8000/api/health  (API docs: /docs)
make frontend     # http://localhost:5173
make test         # backend tests, frontend lint + build
```

To run the backend tests that need the real database: `cd backend && RUN_DB_TESTS=1 .venv/bin/python -m pytest -q`
(they use a separate `decitrace_test` database).

### GitHub ingestion

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/repositories/connect` | `{"url": "https://github.com/psf/requests"}`: validates the URL, checks the repository exists and is public, stores its metadata and starts a background sync |
| GET | `/api/repositories` | connected repositories with their latest sync status |
| GET | `/api/repositories/{id}` | metadata, stored-item counts and the latest sync job |
| POST | `/api/repositories/{id}/sync?full=false` | incremental sync (only what changed since the last one); `full=true` re-reads everything. 409 if a sync is already running |
| GET | `/api/repositories/{id}/sync-status` | per-stage progress, counts and errors |

A sync runs these stages: metadata, issues, issue comments, pull requests (with reviews, review comments
and changed files), discussions, commits, code. Each stage commits on its own, so a failed stage leaves the
others intact and the job ends as `partial`; the next sync retries it.

- **Duplicates and re-downloads:** every row is upserted on GitHub's stable IDs. Reviews and changed files are
  only re-fetched for pull requests whose `updated_at` changed, and file contents only when the blob SHA changed.
- **Code:** DeciTrace reads the git tree, never clones. It skips binaries, lock files, dependency and build folders,
  and files over 200 KB, then fetches decision documents (ADRs, RFCs, README, CONTRIBUTING) first, then other
  docs, manifests and source. Paths are validated against traversal before any request.
- **Rate limits:** the client waits for short resets, honours `Retry-After`, retries 5xx with backoff, and stops
  the sync cleanly when the limit is exhausted.
- **Token:** optional. Without `GITHUB_TOKEN` (60 requests/hour) a sync samples the most recent items and
  skips Discussions, because GitHub's GraphQL API requires authentication. With a token (5,000 requests/hour)
  limits are much higher. The token stays on the server; `/api/health` only reports whether one is set.

## Install the extraction engine

Requires Python 3.9 or newer.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"            # core + tests (no heavy dependencies)
pip install -e ".[embeddings]"     # optional: dense MiniLM embeddings
```

To run with a real model, install [Ollama](https://ollama.com) and pull an open-weight model:

```bash
ollama pull gemma3:1b      # default
ollama pull qwen2.5:1.5b   # alternative
```

## Run

```bash
# 1. download a public thread
decisionlens ingest https://discuss.python.org/t/pep-695-type-parameter-syntax/21646 -o thread.json

# 2. extract decisions with an open-weight model (use --backend heuristic to run with no model)
decisionlens extract thread.json -o decisions.json --model gemma3:1b

# 3. link decisions to a repository's code (rename-aware)
decisionlens link decisions.json --repo /path/to/cpython

# 4. semantic search
decisionlens search decisions.json "why not use angle brackets" --status rejected

# 5. surface decisions for a pull request (local output only)
decisionlens pr decisions.json --repo /path/to/cpython --base main --head my-branch --text "PR description"

# resolve contributor identities across platforms
decisionlens identities accounts.json

# blind evaluation against a PEP's Rejected Ideas section
decisionlens evaluate --pep 695 --model gemma3:1b -o report.json
```

## Examples

`examples/` holds real runs of the tool, not hand-written samples. See [`examples/README.md`](examples/README.md).

**Current blind result on PEP 695** (140-post thread, 5 rejected ideas in the PEP): `qwen2.5:1.5b`
recovered 1 of 5 (precision 50%), `gemma3:1b` recovered 0 of 5, and the rule-based fallback recovered 1 of 5
(all checked by hand). Model size is the bottleneck; see
[`examples/README.md`](examples/README.md) for the full breakdown.

## Tests and CI

```bash
python -m pytest -q
python scripts/validate_examples.py
```

CI (`.github/workflows/ci.yml`) installs the project, runs the unit tests, runs the pipeline end to end
offline, and checks that every quote in the committed example outputs really occurs in the example input.
The tests use a deterministic rule-based backend and a mocked Ollama endpoint, so CI needs no GPU and no
model download.

**macOS note:** with Python 3.13 or newer, macOS can mark the editable-install `.pth` file as hidden, and
Python then skips it (`No module named decisionlens` outside the repo folder). Fix it with
`chflags nohidden .venv/lib/python3.*/site-packages/*.pth`.

## Design notes and honest limitations

- **Open-weight models do the extraction.** Results come from `gemma3:1b` and `qwen2.5:1.5b` run locally
  through Ollama. They are small, so recall on long threads is modest. The same code accepts any Ollama
  model (`--model`), and larger models score higher.
- **The `heuristic` backend is a cue-phrase fallback, not an AI model.** It exists so CI and offline runs are
  deterministic. Outputs are labelled with the backend that produced them.
- **Grounding is lexical.** A paraphrased reason is accepted when 60% of its tokens appear in one sentence of a
  real post. This blocks invented reasons but can occasionally accept a loosely related sentence.
- **Evaluation matching is lexical** (cosine over word sets between the PEP's rejected idea and our
  decision), so scores understate recovery when the thread uses different words than the PEP.
- **Code linking is name-based.** It finds symbols and paths a decision mentions. It does not parse code or
  resolve semantic dependencies.
- **Identity resolution is rule-based** and needs shared emails, links or matching handles. Different handles
  with different names are never merged.
- **Public data only.** The tool only reads public pages and never writes to any project.

## License

MIT, see [LICENSE](LICENSE).
