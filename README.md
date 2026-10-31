# Decentralized Trust Network for Open Source Contributions

> **Problem 7:** Decentralized Trust Network for Open Source Contributions  
> **Category:** Open Source Security | Reputation Systems | Distributed Trust  
> **Team Members:** Mihika Mathur, Saksham Sontakke  

---

## 📌 Project Overview

With the explosion of generative AI coding assistants, open-source repositories are being inundated with automated pull requests, low-effort documentation tweaks, hallucinated library imports, and coordinated spam waves. 

Currently, open-source maintainers evaluate contributors in complete isolation. An abusive bot or serial spammer banned in one repository simply targets another, while legitimate newcomers face heightened suspicion and hostile PR reviews.

**Decentralized Trust Network** is a distributed reputation and threat intelligence framework designed to enable open-source projects to securely exchange contributor trust signals via tamper-evident **vouch** and **denouncement** ledgers, without central gatekeepers.

---

## 🎯 Problem Statement & Why Decentralized Trust is Needed

1. **Siloed Threat Intelligence:** Repositories cannot easily share data on coordinated spam campaigns, leaving maintainers to waste hundreds of hours closing duplicate or AI-hallucinated PRs.
2. **Centralization Risks:** Centralized contributor scoring risks censorship, single points of failure, and corporate capture.
3. **Newcomer Bias:** Strict blanket defenses (such as blocking new accounts) unfairly penalize genuine first-time contributors.
4. **Need for Tamper-Evidence:** Reputation records must be cryptographically verifiable and auditable to prevent defamation or Sybil attacks.

---

## 💡 How the Trust Network Works

```
                     +----------------------------+
                     | Open Source Repositories   |
                     | (Maintainers & Reviewers)  |
                     +--------------+-------------+
                                    |
          +-------------------------+-------------------------+
          |                                                   |
          v                                                   v
+-------------------------+                       +-------------------------+
|   Public Vouch Ledger   |                       | Public Denouncement     |
| (Verifiable Merits/PRs) |                       | Ledger (Abuse Evidence) |
+------------+------------+                       +------------+------------+
             |                                                 |
             +--------------------+----------------------------+
                                  |
                                  v
            +-------------------------------------------+
            |        Decentralized Trust Engine         |
            | - Tamper-Evident SHA-256 Chaining         |
            | - Sybil-Resistant Dampening & Time Decay  |
            | - Guaranteed Newcomer Neutral Baseline    |
            +---------------------+---------------------+
                                  |
                                  v
            +-------------------------------------------+
            | AI Intelligence Pipeline (Planned)        |
            | - all-MiniLM-L6-v2: Semantic Cross-Repo   |
            |   Duplicate & Campaign Detection          |
            | - GPT-4o-mini: Contextual PR Analysis &   |
            |   Explainable Maintainer Assessments      |
            +---------------------+---------------------+
                                  |
                                  v
            +-------------------------------------------+
            | Maintainer Decision & Verification Result |
            +-------------------------------------------+
```

1. **Vouching:** Maintainers publish verifiable vouch records when contributors submit high-value PRs, security audits, or architectural fixes.
2. **Denouncing:** In cases of coordinated spam, bot flooding, or malicious PRs, maintainers publish evidence-backed denouncement records with diff summaries.
3. **Reputation Synthesis:** The trust engine aggregates historical vouches and denouncements, applying diminishing returns (Sybil resistance) and exponential time-decay.
4. **Fair Newcomer Safeguard:** Contributor profiles with zero recorded history automatically receive a neutral baseline score (50.0/100) and `NEUTRAL_NEWCOMER` status, ensuring fair evaluation.

---

## 🚀 Key Features

| Feature | Status | Description |
| :--- | :---: | :--- |
| **Tamper-Evident Record Hashing** | *Planned / Core Design* | Cryptographic SHA-256 canonical hashing ensuring vouch and denouncement auditability. |
| **Fair Newcomer Evaluation** | *Planned / Core Design* | Explicit separation between zero history and negative history to protect authentic newcomers. |
| **Sybil-Resistant Scoring** | *Planned / Core Design* | Diminishing returns on repeated vouches from identical sources to prevent self-collusion. |
| **Cross-Repo Spam Detection** | *Planned (all-MiniLM-L6-v2)* | Semantic embeddings to flag duplicate PR descriptions submitted across distinct repositories within 24h. |
| **AI Assessment Synthesis** | *Planned (GPT-4o-mini)* | Natural language summaries explaining contributor credibility to maintainers. |

---

## 🛠 Technology Stack

- **Data Formats & Standards:** JSON Schema, SHA-256 canonical payload hashing
- **Language & Runtime:** Python 3.10+
- **Planned ML Architecture:**
  - `sentence-transformers/all-MiniLM-L6-v2`: Dense semantic vector search for cross-repo duplicate detection
  - `GPT-4o-mini`: Natural language reasoning over evidence summaries and review explanations
- **CI/CD:** GitHub Actions for automated validation and schema verification

---

## 📂 Repository Structure

```text
Hackbotter_final/
├── LICENSE                                # MIT Open Source License
├── HACKATHON.md                           # Hackathon submission details & model justifications
├── README.md                              # Project overview & execution guide
├── .gitignore                             # Environment and build artifact ignores
├── .github/
│   ├── pull_request_template.md           # Mandatory PR template for contributions
│   └── workflows/
│       └── ci.yml                         # Automated validation workflow
└── examples/
    ├── sample_vouch.json                  # Sample vouch input payload
    ├── sample_vouch_output.json           # Sample vouch ledger output record
    ├── sample_denouncement.json           # Sample denouncement input payload
    ├── sample_denouncement_output.json    # Sample denouncement ledger output record
    ├── sample_spam_scan_input.json        # Sample PR cross-repo spam scan input
    └── sample_spam_scan_output.json       # Sample cross-repo campaign detection output
```

---

## ⚙️ Setup & Execution Instructions

### Prerequisites
- Python 3.10 or higher
- Git

### 1. Clone the Repository
```bash
git clone https://github.com/CyborgX-hash/MLH.git
cd Hackbotter_final
```

### 2. Validate Example Schemas
You can test the integrity of example payloads directly using Python:
```bash
python3 -m json.tool examples/sample_vouch.json > /dev/null && echo "Vouch payload valid!"
python3 -m json.tool examples/sample_denouncement.json > /dev/null && echo "Denouncement payload valid!"
python3 -m json.tool examples/sample_spam_scan_output.json > /dev/null && echo "Spam scan output valid!"
```

---

## 💡 Example Use Cases

### 1. Fast-Tracking a Vouched Contributor
When `@alex_developer` submits a PR to an open-source project, the maintainer queries the trust network. The network reveals verified vouches from two major repositories for critical bug fixes. The maintainer can confidently prioritize reviewing and merging the PR.

### 2. Blocking Coordinated Multi-Repo Spam Waves
A bot cluster generates 20 PRs with generic titles (*"Update README.md formatting"*) across 10 unrelated repositories. The semantic spam scanner matches text embeddings with high similarity across distinct repositories within a 24-hour window, automatically flagging the campaign ID (`CAMP-74102`) and alerting maintainers.

### 3. Fairly Welcoming a First-Time Contributor
A first-time contributor `@genuine_coder` creates their very first GitHub PR. With zero prior records, the trust engine marks them as `NEUTRAL_NEWCOMER` with baseline trust (50.0/100). The maintainer reviews the PR on its technical merits without bias.

---

## 👥 Team Information

- **Mihika Mathur**
- **Saksham Sontakke**
- **Repository:** [https://github.com/CyborgX-hash/MLH.git](https://github.com/CyborgX-hash/MLH.git)
- **License:** [MIT License](LICENSE)
