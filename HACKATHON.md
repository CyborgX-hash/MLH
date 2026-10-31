# Hackathon Submission

## Team Information
- **Team Name:** Commit Crimes
- **Members:**
  - Mihika Mathur
  - Saksham Sontakke

## Selected Problem
- **Problem ID:** 06
- **Problem Name:** Open Source Decision Intelligence and Knowledge Recovery
- **Category:** Knowledge Management | Developer Intelligence | Information Retrieval

## Problem Overview
Open-source software projects generate thousands of critical technical discussions across GitHub issues, pull requests, code reviews, and community threads. Over time, crucial architectural decisions, trade-offs, and explicitly rejected alternatives become buried in closed threads. 

When new contributors or maintainers join or attempt architectural changes, they often:
1. Re-propose solutions that were already thoroughly evaluated and rejected in the past.
2. Miss crucial context on why specific architectural patterns or constraints were chosen.
3. Lack direct traceability between lines of production code and the underlying human decisions that produced them.

Without automated decision extraction, historical knowledge is lost to developer turnover and voluminous discussion archives.

## Our Objective
Our objective is to build an intelligent knowledge recovery platform that automatically captures, structures, and surfaces historical technical decisions:
- **Extract Technical Decisions:** Parse unstructured developer discussions to isolate concrete technical decisions and architectural consensus.
- **Recover Rejected Alternatives:** Systematically capture discarded options along with the specific reasons, trade-offs, and failure modes identified by the team.
- **Link Decisions to Code:** Correlate extracted decisions directly to relevant files, modules, and commit references in the codebase.
- **Preserve Discussion Traceability:** Anchor every decision record to its original source URL, author, and timestamp for verifiable auditability.
- **Proactive PR Retrieval:** Retrieve and surface relevant historical decisions when new pull requests or issues touch related areas of the system.
- **Evidence-Backed Traceability:** Guarantee that all extracted knowledge remains traceable to verifiable discussion records.

## AI Models and Justification

Only open-weight models are used. Each entry states plainly whether it is integrated and used today.

### 1. gemma3:1b (Google Gemma 3, open weights), served locally by Ollama
- **Status:** Integrated and used. This is the default extraction model (`decisionlens extract --model gemma3:1b`). The committed example `examples/sample_output.json` was produced by it.
- **What it does:** Reads chunks of a discussion thread and returns candidate decisions as schema-constrained JSON: idea, stance (accepted, rejected, deferred, open), reasons, cited post and quote.
- **Why we chose it:** Runs on a laptop CPU through Ollama, supports JSON-schema-constrained output, and the open weights keep all data local. It processes a 140-post thread in about 4.5 minutes.
- **Known limit:** Its recall on long threads is low (see `examples/README.md`). The pipeline accepts any Ollama model through `--model`.

### 2. qwen2.5:1.5b (Alibaba Qwen 2.5, open weights), served locally by Ollama
- **Status:** Integrated and used as the alternative extraction model (`--model qwen2.5:1.5b`). Its run on the same thread is committed for comparison.
- **Why we chose it:** Strong instruction following and structured-output behaviour for its size; a second model family to compare against.

### 3. sentence-transformers/all-MiniLM-L6-v2 (open weights)
- **Status:** Integrated in code as an optional dependency (`pip install -e ".[embeddings]"`). It is used for semantic search and PR matching when installed. **The committed examples and CI use the built-in TF-IDF fallback instead**, so this model did not produce any committed output.
- **Why we chose it:** Small (384-dimensional), fast on CPU, good semantic retrieval quality for technical prose.

### Planned (not yet integrated)
- **Qwen3-8B** (open weights) through a configurable OpenAI-compatible provider, for the DeciTrace web platform. It will be listed as integrated only when it is.

### Not an AI model
- The `heuristic` backend is a deterministic cue-phrase extractor used for offline CI runs and tests. It is reported as `heuristic` in every output and is never presented as a model.

## AI Coding Assistants
- Claude Code (Anthropic) helped write the code, tests and documentation.
