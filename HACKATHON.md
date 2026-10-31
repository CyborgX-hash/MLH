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

> **Implementation Status Note:** The models listed below are **proposed architectural choices** planned for the intelligence and extraction pipeline. They are not claimed to be fully integrated into production at this stage.

### 1. GPT-4o-mini
- **Status:** Proposed / Planned Model
- **Intended Purpose:**
  - **Decision Extraction:** Parsing natural language discussion threads to isolate technical consensus from conversational chatter.
  - **Discussion Summarization:** Generating concise summaries of complex technical debates and trade-offs.
  - **Classification of Approaches:** Distinguishing between accepted solutions, rejected alternatives, and deferred proposals.
  - **Reasoning Extraction:** Identifying explicit rationales, performance implications, and trade-offs behind each decision.
- **Reason for Selection:**
  - Superior reasoning capability for structured information extraction from long developer dialogues.
  - Cost-effective and fast inference suitable for scanning extensive issue and PR histories.
  - Strong adherence to strict JSON extraction schemas.

### 2. sentence-transformers/all-MiniLM-L6-v2
- **Status:** Proposed / Planned Model
- **Intended Purpose:**
  - **Text Embeddings:** Generating dense vector representations of extracted decision summaries, contexts, and technical keywords.
  - **Semantic Search:** Enabling conceptual search across historical decisions rather than rigid keyword matching.
  - **Similarity-Based Retrieval:** Powering real-time recommendation of historical decisions for newly opened pull requests and issues.
- **Reason for Selection:**
  - Fast, lightweight embedding generation with 384-dimensional dense vectors.
  - Capable of running locally or at the edge with minimal resource overhead.
  - High semantic retrieval accuracy for developer terminology and code-adjacent technical prose.
