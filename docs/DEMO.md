# DeciTrace: judge demo kit

Everything below uses the real public repository [`psf/requests`](https://github.com/psf/requests). Every step
was run on the development machine before this script was written. Where the real data shows a limitation, the
script says so instead of hiding it.

## Before the demo (10 minutes, once)

1. `make db && make migrate`, then `make backend` and `make frontend`.
2. In `.env`, use the hosted open-weight model: `AI_PROVIDER=openrouter`, `AI_BASE_URL=https://openrouter.ai/api/v1`,
   `AI_MODEL=qwen/qwen3.6-27b`, `AI_EXTRACT_MODEL=qwen/qwen3.6-27b`, `AI_EMBED_MODEL=` (full-text retrieval),
   `AI_EXTRA_BODY={"reasoning": {"enabled": false}}` and your `AI_API_KEY`.
3. **Set `GITHUB_TOKEN`.** Without it GitHub allows 60 requests per hour *per network*; on shared Wi-Fi the
   quota can already be used up, and the live connect step will show the rate-limit message instead.
4. Pre-ingest so the demo does not wait on the network: connect `https://github.com/psf/requests`, wait for
   **Processing completed**, then press **Extract decisions** once.
5. Open these tabs: the dashboard, decision "Where to declare type annotations on Response attributes",
   [psf/requests#7271](https://github.com/psf/requests/issues/7271), and the Ask page.

## The 3-minute demo

| Time | Show | Say |
|---|---|---|
| 0:00 | Landing page | "Why code is the way it is lives in old issue threads. DeciTrace recovers it, with evidence." |
| 0:15 | **Repositories**: paste `https://github.com/psf/requests`, press Connect (or open the pre-connected one) | "Public repos only, read-only. It never posts to GitHub." |
| 0:30 | **Dashboard**: sync stages and counts (129 discussions, 611 comments) | "Issues, PRs, reviews, comments, commits and key files, linked together and indexed." |
| 0:45 | **Decision extraction** panel: 5 threads, 8 candidates, 5 decisions | "Qwen3.6-27B, an open-weight model, proposes decisions. Our validator checks every citation before anything is recorded. Notice they are all *unresolved*: the model thought some options were chosen, but no maintainer said so explicitly, so a human confirms them." |
| 1:05 | **Decisions** → open "Where to declare type annotations on Response attributes" | "This is a real RFC thread, #7271." |
| 1:15 | Alternatives (both *proposed*), contributors, **Timeline** | "The extractor claimed one option was selected and the other rejected. The rules downgraded both, because no maintainer stated an outcome in explicit words. The maintainer's closing comment is shown as 'cited as a resolution, not an approval'." |
| 1:35 | Click **source on GitHub** on the objection | Opens the maintainer's real comment: "every line on screen comes from a real comment." |
| 1:45 | **Graph** view, then "Implementation" section | "Contributors, threads, alternatives and links. This decision has *No verified implementation evidence found*: it was deferred to another project, and DeciTrace says so instead of matching keywords." |
| 2:00 | **Ask DeciTrace**: "Why does requests declare type annotations at class level on Response instead of in `__init__`?" | "Answers use only retrieved evidence. Citations are mapped to real GitHub URLs by the backend; the model cannot invent links. This one is rated *partial* because the decision is unresolved." |
| 2:25 | **Conflict review** | "Both sides, with their original comments. DeciTrace never picks a winner. A maintainer resolves it with their own GitHub token, and GitHub confirms they have write access." |
| 2:45 | **PR impact**: paste a requests PR URL | "Paste a pull request and DeciTrace lists the recorded decisions it touches, as review prompts only. It never blocks a PR." |
| 3:00 | End | "Evidence first, AI second, humans decide." |

Notes for the presenter:
- The decision for #7271 was written by hand from the real comments, because the 1.5B model could not produce a
  usable one. It went through the same validator; say so if asked (`created_by: extractor:manual-ui-check`).
- The PR impact step lists findings only for decisions with implementation links. With the current `psf/requests`
  decisions it will truthfully report that no recorded decision is linked; the conflict path is covered by
  automated tests (`backend/tests/test_pr_impact.py`).
- The live Connect step needs GitHub quota; if it shows the rate-limit message, point at the message ("we handle
  it, with the reset time") and continue with the pre-connected repository.

## 30-second pitch

Open-source projects make their most important decisions in issue threads and review comments, then lose them.
New contributors re-propose rejected ideas, and the reasoning leaves with the people who wrote the code.
DeciTrace connects to a GitHub repository and recovers those decisions: what was chosen, what was rejected and
why, who argued what, and where it was implemented. An open-weight model only proposes. Every claim is checked
against the original comment, disagreements stay unresolved until a maintainer settles them, and every answer
links back to GitHub.

## 1-minute architecture

A background worker reads the repository through GitHub's REST and GraphQL APIs, read-only, and stores issues,
PRs, reviews, comments, discussions, commits and selected files in PostgreSQL. A linker connects records through
explicit references such as "closes #12", which count as verified, and through shared files or terms, which
count only as possible. An indexer builds full-text vectors and optional pgvector embeddings.

For extraction, an open-weight model served by Ollama reads one thread at a time and returns candidate decisions
as JSON citing message ids. Every candidate passes through the evidence validator, which is plain code, before
anything is stored. On top of the stored decisions sit:
- code mapping through merged PRs, following renames;
- a timeline and a graph;
- human review with GitHub-verified permissions;
- PR impact analysis;
- a RAG question-answering endpoint.

The frontend is React with TypeScript.

## The RAG pipeline

1. **Index.** After each sync, decisions, issues, PRs, discussions, comments, commits and key files become
   chunks. Each has a PostgreSQL full-text vector and, if an embedding model is configured, a pgvector
   embedding. Unchanged chunks keep their embeddings.
2. **Retrieve.** For a question: SQL filters (repository, kind, decision status), full-text ranking with OR
   semantics, and pgvector cosine similarity, fused by reciprocal rank fusion. Validated decisions rank higher.
   Without embeddings it falls back to full-text and says so.
3. **Expand.** Each retrieved decision brings its verified evidence comments, its alternatives (an unrecorded
   rejection reason is written as "not recorded") and its implementation status.
4. **Generate.** The model sees numbered `<source>` blocks marked as untrusted and must answer only from them,
   cite `[S1]`, keep conflicts unresolved and say when evidence is incomplete. It never writes URLs.
5. **Guard.** The backend maps citation ids to stored GitHub URLs, deletes ids and links it did not provide, and
   withholds an answer that cites nothing. It computes confidence itself: *supported* only when a verified,
   explicitly established decision is cited. With no relevant evidence the model is not called.

## The evidence validation system

The model's output is a *candidate*. For every citation the validator checks:
- that the id has DeciTrace's format (otherwise it is fabricated);
- that the record exists and belongs to this repository;
- that its stored URL is the original `github.com/<owner>/<repo>` URL (a URL claimed by the model is ignored);
- that the quote really occurs in the stored text;
- that the text supports the claim.

Each citation becomes *verified*, *partially verified* or *unsupported*, and unsupported ones are kept, flagged.

Fixed rules then set the status, regardless of what the model claimed:
- **Explicit** only when an owner, member or collaborator states the outcome, naming it without negation
  ("PostgreSQL, not MongoDB" can never establish MongoDB), or approves the PR that implements it.
- **Inferred** when only a merged PR or commit supports it.
- Otherwise **unresolved**. Competing proposals from different people are a conflict, and votes are never counted.
- An alternative is **rejected** only with a recorded objection; otherwise it was "considered, not selected".

A candidate with no verifiable evidence is refused outright. Only a reviewer whose write access GitHub confirms
can record a different outcome, and every change is audited.

## Why this is not GitHub search or an AI summary

- **GitHub search** finds words. It cannot tell a proposal from a decision, or say what was rejected and why.
- **An AI summary** tells you what a model believes. It can invent a consensus, merge opposing views, or cite
  nothing. You cannot check it without re-reading the thread.
- **DeciTrace** keeps the model as a proposer and puts deterministic checks between the model and the record.
  Every statement links to the comment it came from; disagreement is preserved, not averaged; "we don't know"
  is a valid answer. It also connects the decision to code and to future pull requests, which neither search nor
  summaries do.

## Honest limitations and future work

- **Model size is the bottleneck.** On an 8 GB laptop only a 1.5B model fits next to the database, and it
  extracts poorly: in our real run most candidates were refused. Qwen3-8B, the configured default, needs about
  16 GB. Future work: run on a GPU host, and add model-assisted stance detection, which would still not be
  model-decided.
- **Lexical rules under-claim.** Real decisions phrased unusually (for example "we're going to defer the patch")
  stay unresolved until a human confirms them. PR impact can miss reworded conflicts.
- **Rate limits.** Without `GITHUB_TOKEN`, ingestion is sampled and Discussions are skipped.
- **No user accounts.** Keep it on localhost or behind an authenticating proxy. Future work: GitHub OAuth for
  reviewers and per-user rate limits.
- Future work: an opt-in GitHub App that posts PR impact as a non-blocking review comment, wiring the engine's
  cross-platform identity resolution into the platform, and evaluating on more PEPs and RFCs.
