# Hackathon Submission

## Team Information
- **Team Name:** [TEAM NAME]
- **Team Members:**
  - Mihika Mathur
  - Saksham Sontakke

## Selected Problem Statement
- **Problem Statement:** Problem 7 – Decentralized Trust Network for Open Source Contributions
- **Category:** Open Source Security | Reputation Systems | Distributed Trust
- **Problem Description:**  
  AI-powered development tools have made it easier to generate large volumes of code, issues, and pull requests. This has increased the risk of low-quality contributions, spam, and coordinated abuse targeting multiple open-source repositories. Individual open-source projects generally evaluate contributors independently and cannot easily share reputation information.
- **Project Objective:**  
  We aim to build a decentralized trust network that allows open-source projects to exchange contributor reputation signals through public vouch and denouncement records. The system will identify suspicious contribution patterns across repositories, detect coordinated spam campaigns, and provide fair reputation evaluation without automatically penalizing legitimate newcomers.

## Proposed Solution
We propose a decentralized trust network for open-source repositories designed to protect project maintainers while encouraging authentic contributors. Key capabilities include:
- **Public Vouch Records:** Verifiable endorsements published by repositories and maintainers acknowledging credible and positive contributions.
- **Public Denouncement Records:** Evidence-backed records documenting instances of spam, automated low-quality contributions, or malicious activity.
- **Cross-Project Reputation Exchange:** Inter-repository sharing of contributor trust signals, enabling maintainers to benefit from community-wide reputation insights.
- **Trust Propagation:** Weighted network trust propagation based on mutual project endorsements, maintainer standing, and historical verification.
- **Coordinated Spam Campaign Detection:** Cross-repository telemetry to detect coordinated spam campaigns and automated bot attacks spanning multiple projects.
- **Fair Evaluation of New Contributors:** Distinction between an unestablished track record and negative reputation, ensuring legitimate newcomers are evaluated fairly without premature penalization.

## AI Models Used / Selected

> **Note on Implementation Status:** The models below represent our initially selected and planned AI architecture. They are not yet integrated or implemented into the codebase.

### Model 1: GPT-4o-mini
- **Status:** Planned / Initially Selected
- **Intended Purpose:**
  - Analyze contributor behavior and contribution context.
  - Assist in identifying suspicious contribution patterns.
  - Explain reputation assessments in natural language for maintainers.
  - Analyze evidence associated with vouch and denouncement records.
- **Reason for Selection:**
  - Excellent balance between reasoning capabilities, response latency, and API operational cost.
  - Well-suited for structured analysis, context synthesis, and classification tasks.
  - Generates clear, human-understandable explanations that maintainers can review to make informed decisions.

### Model 2: sentence-transformers/all-MiniLM-L6-v2
- **Status:** Planned / Initially Selected
- **Intended Purpose:**
  - Generate dense semantic embeddings for pull request descriptions, commit messages, and issue reports.
  - Identify semantic similarity across contribution descriptions to flag template reuse.
  - Compare suspicious contribution patterns across multiple repositories.
  - Help detect potentially duplicated, low-effort, or coordinated submissions.
- **Reason for Selection:**
  - Lightweight and highly efficient embedding model.
  - Delivers fast semantic similarity search performance at scale.
  - Capable of processing large volumes of contribution records.
  - Runs locally without requiring external or paid embedding API services.

## Initial Development Goals
- **Contributor Reputation Management:** Implementing data structures and logic for tracking, scoring, and maintaining contributor trust profiles.
- **Project-to-Project Trust Exchange:** Creating federated exchange protocols and querying interfaces for cross-project reputation sharing.
- **Evidence-Backed Reputation Records:** Anchoring vouch and denouncement entries with concrete, auditable evidence (pull requests, commit diffs, review logs).
- **Cross-Repository Suspicious Activity Detection:** Semantic clustering and temporal analysis to pinpoint cross-repository coordinated spam waves.
- **Reputation Evaluation and Visualization:** Developing maintainer tooling and visual dashboards for transparent, explainable reputation insights.

