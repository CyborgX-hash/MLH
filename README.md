# Open Source Decision Intelligence and Knowledge Recovery

> **Hackathon Submission:** Problem 06 – Open Source Decision Intelligence and Knowledge Recovery  
> **Category:** Knowledge Management | Developer Intelligence | Information Retrieval  
> **Team Name:** Commit Crimes  
> **Team Members:** Mihika Mathur, Saksham Sontakke  

---

## 📌 Project Overview

In open-source software engineering, key architectural decisions, performance trade-offs, and critical constraints are thoroughly debated in GitHub issues, pull request review threads, and developer discussions. 

However, once a pull request is merged or a discussion is closed, that hard-won knowledge becomes buried under thousands of subsequent commits and comments. When new contributors join or architectural components evolve, teams frequently:
- **Re-litigate already settled debates:** Re-proposing patterns that were previously tested, evaluated, and rejected.
- **Lose context on system constraints:** Modifying critical paths without understanding historical failure modes or design trade-offs.
- **Suffer from developer turnover:** Valuable institutional memory vanishes when maintainers step down.

**Commit Crimes** is designing an intelligent knowledge recovery and decision intelligence framework that extracts technical decisions, catalogues rejected alternatives with explicit justifications, links decisions to source code references, and surfaces relevant historical knowledge directly during code review.

---

## 🎯 Problem Statement

**Problem 06:** Open Source Decision Intelligence and Knowledge Recovery

Traditional search engines and keyword-based repository search struggle to differentiate between idle chatter, exploratory proposals, and binding architectural consensus. Open-source communities need an automated pipeline that can:
1. Parse unstructured discussions across issues, PRs, and team threads.
2. Differentiate accepted decisions from rejected alternatives and exploratory queries.
3. Preserve full attribution and verifiable evidence links back to the original messages.
4. Connect historical decisions to specific files, modules, and functions.
5. Proactively notify developers during PR review when proposed changes conflict with historical decisions.

---

## 💡 System Workflow

The end-to-end knowledge recovery pipeline processes technical discussions into queryable, code-linked decision records:

```text
GitHub Discussions
       |
       v
Discussion Collection
       |
       v
Preprocessing
       |
       v
AI Decision Extraction
       |
       v
Decision Classification
       |
       v
Knowledge Storage
       |
       v
Semantic Retrieval
       |
       v
Decision-to-Code Linking
       |
       v
Developer Dashboard / PR Intelligence
```

### Workflow Steps
1. **Discussion Collection:** Ingest raw conversation threads from GitHub Discussions, Issue comments, and PR review exchanges.
2. **Preprocessing:** Normalize messages, strip extraneous markdown/bot noise, and structure chronological interaction trees.
3. **AI Decision Extraction:** Employ language models to distinguish key decision points from conversational chatter.
4. **Decision Classification:** Categorize options into accepted solutions, rejected alternatives, deferred concepts, or experimental trials.
5. **Knowledge Storage:** Store structured decision records with deterministic IDs, metadata, and timestamps.
6. **Semantic Retrieval:** Embed decision summaries into dense vector representations for conceptual search.
7. **Decision-to-Code Linking:** Correlate extracted architectural patterns with affected files, components, and symbol paths.
8. **Developer Dashboard / PR Intelligence:** Surface relevant prior decisions in pull request reviews and developer portals.

---

## 🚀 Core Features

| Feature | Status | Description |
| :--- | :---: | :--- |
| **Technical Consensus Extraction** | *Planned* | Automatically identifies agreed-upon design patterns from lengthy multi-contributor dialogues. |
| **Rejected Alternative Recovery** | *Planned* | Extracts rejected approaches, benchmarking results, and the exact reasons why alternatives were dismissed. |
| **Verifiable Evidence Attribution** | *Planned* | Links every extracted decision point to its exact source message, author, and timestamp. |
| **Codebase Cross-Linking** | *Planned* | Maps architectural decision records (ADRs) to impacted source files and modules. |
| **Semantic Historical Retrieval** | *Planned* | Retrieves contextually relevant past decisions when reviewing newly submitted PRs. |

---

## 🤖 AI Models & Responsibilities

> **Status Notice:** The models listed below represent our **proposed architectural choices**. They are documented here to outline their planned integration into our processing pipeline.

### 1. GPT-4o-mini
- **Role:** Deep Decision Parsing & Reasoning Extraction
- **Responsibilities:**
  - Ingests preprocessed developer discussions and isolates consensus conclusions.
  - Summarizes multi-party debates into structured ADR-style summaries.
  - Classifies approaches into `ACCEPTED`, `REJECTED`, or `DEFERRED`.
  - Extracts explicit technical justifications (e.g., latency constraints, memory bounds, security trade-offs).
- **Selection Rationale:** Provides strong reasoning and structured output generation at low inference cost and high processing speed.

### 2. sentence-transformers/all-MiniLM-L6-v2
- **Role:** Dense Semantic Vector Embedding & Retrieval
- **Responsibilities:**
  - Converts decision contexts, problem statements, and technical keywords into 384-dimensional dense vectors.
  - Enables semantic similarity matching across PR descriptions and existing decision archives.
  - Detects duplicate proposals or re-emerging rejected architectures.
- **Selection Rationale:** Lightweight, edge-deployable embedding model running locally without recurring API costs.

---

## 🛠 Technology Stack

- **Data Formats:** JSON / JSON Schema, Markdown
- **Target Language & Runtime:** Python 3.10+
- **Planned Natural Language Stack:**
  - `openai` Python SDK (targeting `gpt-4o-mini`)
  - `sentence-transformers` (targeting `all-MiniLM-L6-v2`)
- **Validation & CI/CD:** GitHub Actions for automated linting, schema validation, and deliverables verification.

---

## 📂 Repository Structure

```text
Hackbotter_final/
├── LICENSE                                # MIT Open Source License
├── HACKATHON.md                           # Team information, problem selection & model justification
├── README.md                              # Project overview, workflow, and architecture documentation
├── .github/
│   ├── pull_request_template.md           # Mandatory PR template with historical decision checklist
│   └── workflows/
│       └── ci.yml                         # Automated validation and payload testing workflow
└── examples/
    ├── sample_input.json                  # Sample multi-contributor technical discussion input
    └── sample_output.json                 # Illustrative structured decision record output
```

---

## ⚙️ Installation & Setup

### Prerequisites
- Python 3.10 or higher
- Git

### 1. Clone the Repository
```bash
git clone https://github.com/CyborgX-hash/MLH.git
cd Hackbotter_final
```

### 2. Validate Deliverables & JSON Examples
You can test the integrity and syntax of the provided sample input and output files using Python's built-in JSON validation:
```bash
python3 -m json.tool examples/sample_input.json > /dev/null && echo "sample_input.json is valid!"
python3 -m json.tool examples/sample_output.json > /dev/null && echo "sample_output.json is valid!"
```

---

## 💡 Example Use Cases

### 1. Preventing Re-Litigation of Rejected Proposals
A new contributor opens a pull request proposing to replace an in-memory buffer with an external Redis cluster. The decision recovery engine searches historical records, finds `DEC-2024-0012` where an external Redis tier was rejected due to P99 network latency SLA breaches, and automatically alerts the reviewer.

### 2. Accelerated Onboarding for Maintainers
A newly appointed subsystem maintainer needs to understand why specific caching algorithms or bounded memory limits exist in `ingestion/routing/cache_manager.py`. The tool maps the code back to original GitHub discussion threads, providing the full context of the decision in seconds.

### 3. Automated Architectural Decision Records (ADRs)
Instead of relying on developers to manually author and maintain ADR documents, the platform periodically scans merged PRs and closed discussions, drafting structured decision records for maintainer approval.

---

## 👥 Team Information

- **Team Name:** Commit Crimes
- **Team Members:**
  - Mihika Mathur
  - Saksham Sontakke
- **Repository:** [https://github.com/CyborgX-hash/MLH.git](https://github.com/CyborgX-hash/MLH.git)
- **License:** [MIT License](LICENSE)
