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

### Evidence validation and human review

An extractor (AI or otherwise) can only submit a **candidate**: topic, decision, alternatives, reasons,
positions and the sources it cites (`comment:<id>`, `issue:<id>`, `pull_request:<id>`, `discussion:<id>`,
`commit:<id>`). The backend then checks every citation independently:

| Check | Failure flag |
|---|---|
| The ID has DeciTrace's format | `fabricated_id` |
| The source exists | `source_not_found` |
| It belongs to this repository (other repositories' data is never shown) | `wrong_repository` |
| Its stored URL is the original `github.com/<owner>/<repo>/…` URL; a URL claimed by the extractor is never used | `non_github_url`, `url_mismatch` |
| The quoted text really appears in the stored text | `quote_not_found`, `quote_paraphrased` |
| The text supports the claim | `weak_support`, `does_not_support_claim` |

Each citation becomes `verified`, `partially_verified` or `unsupported`, and unsupported ones are stored
(flagged), not dropped. Fixed rules then set the outcome, whatever the extractor claimed:

- **Explicit** only when a verified statement by an owner, member or collaborator states the outcome (or a
  maintainer's approving review). A non-maintainer saying "let's go with X" is not a decision.
- **Inferred** when the only support is a merged PR or commit: shown as "not explicitly approved", needs review.
- **Unresolved** otherwise. Competing proposals or opposing stances from different people mark a conflict.
  Vote counts are never used.
- An alternative is **rejected** only with verified objection evidence; otherwise it was "considered, not selected"
  (or "proposed" while unresolved). An unverified rejection reason is stored as null.
- A candidate with no verifiable evidence at all is refused: no decision record is created.

Human review: `POST /api/decisions/{id}/reviews` with the reviewer's own GitHub token in `X-GitHub-Token`.
GitHub confirms who they are (`GET /user`) and their access to the repository; write access or higher is
required. The token is used for those two calls only and never stored. Every review records reviewer,
permission, time, outcome and explanation, and the audit log keeps a snapshot of the decision before each
change. `POST /api/decisions/{id}/supersede` marks a decision as replaced by a newer one.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/repositories/{id}/decisions/validate` | dry run: the validation report, nothing stored |
| POST | `/api/repositories/{id}/decisions` | validate and record (422 with the report if unsupported) |
| GET | `/api/repositories/{id}/decisions` | decisions, those needing review first |
| GET | `/api/decisions/{id}` | alternatives, evidence, positions, reviews, history |
| POST | `/api/decisions/{id}/reviews` | authorised human outcome |
| POST | `/api/decisions/{id}/supersede` | replace by a newer decision |

### Linking discussions to one another and to code

After every sync, DeciTrace rebuilds a graph between issues, pull requests, discussions and commits.

| Signal | Relation | Status |
|---|---|---|
| `#12`, `owner/repo#12` (same repository only), issue/PR/discussion URLs | `references` (`discusses` from a discussion) | verified |
| `closes/fixes/resolves #12` in a PR or commit | `implements` | verified |
| `supersedes #20`, `superseded by #30` | `supersedes` | verified |
| `reverts #12`, `conflicts with #12`, `This reverts commit <sha>` | `conflicts_with` | verified |
| commit `Title (#25)` / `Merge pull request #25`, PR merge-commit SHA | `references` | verified |
| a file path mentioned in an issue that a PR changed | `related_to` | possible |
| two or more shared rare technical terms | `related_to` | possible |
| text similarity alone | `related_to` (low confidence) | possible |

Every link stores its evidence (snippet and URL, paths or terms). Code blocks are ignored, numbers that do not
exist are never linked, and possible links are shown as "possible connections", never as facts. A candidate
decision whose sources are explicitly linked to an existing decision on the same topic is merged into it
instead of creating a duplicate; if it suggests a different outcome, the decision is flagged for review.

**Decision-to-code mapping** follows change records only: merged PRs or commits that the decision cites, or
that are explicitly linked to its sources (closing keywords, commit references, merge commits). Each changed
file keeps its PR and commit links and is followed through later merged PRs: renamed (current path shown),
deleted, or changed again. Unmerged PRs never count, and file contents are never keyword-matched. Possible
mappings are listed separately. With no verified link the API says "No verified implementation evidence found."

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/repositories/{id}/links/rebuild` | recompute the link graph |
| GET | `/api/repositories/{id}/links` | links, filterable by record and status |
| GET | `/api/decisions/{id}/related` | the decision's history across sources |
| GET | `/api/decisions/{id}/code` | verified and possible implementation (recomputed per request) |
| GET | `/api/repositories/{id}/files/decisions?path=` | decisions implemented in a file, under its old or new name |

### Asking questions (RAG)

Connecting a repository needs no question: each sync ends by building a knowledge base of chunks from
decisions, issues, PRs, discussions, comments, commits and key files. Each chunk has a PostgreSQL full-text
vector and, when an embedding model is available, a pgvector embedding. Unchanged chunks keep their embeddings.

`POST /api/repositories/{id}/ask` with `{"question": "..."}`:

1. **Hybrid retrieval:** SQL filters (repository, kind, decision status) plus full-text ranking plus pgvector
   cosine similarity, fused with reciprocal rank fusion. Validated decisions rank above raw discussion.
   Without an embedding model it falls back to full-text search and says so in `warnings`.
2. **Evidence expansion:** each retrieved decision brings its verified evidence comments, its alternatives (an
   unrecorded rejection reason is stated as such) and its implementation status from the code map.
3. **Grounded generation:** the model sees numbered sources `[S1]…[Sn]` and must answer only from them, keep
   unresolved conflicts unresolved, say when evidence is incomplete, and never write URLs.
4. **Backend guardrails:**
   - Citation IDs are mapped to the stored GitHub URLs.
   - Invented IDs and links are removed.
   - An answer that cites nothing is withheld.
   - With no relevant evidence, the model is not called at all.
   - `confidence` is computed by the backend: `supported` (cites a verified, explicitly established decision),
     `partial` (cites only raw records), or `insufficient`.

```json
{
  "answer": "…[S1]…",
  "citations": [{"id": "S1", "source_type": "issue", "source_number": 12, "url": "https://github.com/…", "evidence": "…"}],
  "confidence": "supported",
  "insufficient_evidence": false,
  "conflicts": [], "decisions": [], "warnings": [], "retrieval": {"mode": "hybrid", "hits": 12}, "model": "qwen3:8b"
}
```

To enable vector search and the default answer model with Ollama:

```bash
ollama pull qwen3:8b
ollama pull qwen3-embedding:0.6b
```

Any other OpenAI-compatible server or hosted provider works through `AI_BASE_URL`, `AI_MODEL` and `AI_API_KEY`.

**Memory:** Qwen3-8B needs about 6 GB and the embedding model about 2.4 GB once loaded. On an 8 GB machine that
also runs PostgreSQL in Docker, the system ran out of swap and PostgreSQL restarted mid-write. It recovered cleanly
from its WAL, but use a 16 GB machine, a smaller model (`AI_MODEL=qwen2.5:1.5b` works) or a remote
OpenAI-compatible endpoint for the models.

### Web interface

The frontend (React, Vite, TypeScript, Tailwind) is dark-first with a light theme, and every page reads the real API:

| Page | Route | What it shows |
|---|---|---|
| Landing | `/` | the problem, how it works, features, an example history clearly labelled as illustrative |
| Repositories | `/connect` | URL input with validation errors and loading state, public/private and rate-limit notes, connected repositories |
| Dashboard | `/repos/:id` | discussions collected, decisions, unresolved decisions, rejected alternatives, sync stages, recent decision activity |
| Decision explorer | `/repos/:id/decisions` | filters (accepted, rejected, proposed, unresolved, superseded) and search; selected and rejected alternatives, evidence quality, review status |
| Decision detail | `/repos/:id/decisions/:decisionId` | problem, proposals, arguments, positions, contributors, related records, implementing PRs, commits and files, **timeline** and **graph**, audit history, review form |
| Ask DeciTrace | `/repos/:id/ask` | chat with suggested questions, cited answers, conflict warnings, a "no evidence" state |
| Conflict review | `/repos/:id/conflicts` | contested or unestablished decisions with both sides' original comments and the authorised review action |

The timeline (`GET /api/decisions/{id}/timeline`) and graph (`GET /api/decisions/{id}/graph`) are built only from
stored evidence, links, code links, reviews and supersede pointers, so they never show a relationship the backend
has not established. Every timeline event links to its GitHub source. Only a validator-established approval is
shown as "Approval". The graph shows verified relationships by default; possible connections (dashed) appear
only when the reader turns them on. Unresolved and inferred decisions are never shown in green.
AI errors map to clear HTTP codes: model unavailable 503, timeout 504, rate limit 429, context too long 413,
invalid output 502 after one corrective retry.

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
