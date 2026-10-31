# DeciTrace platform example: psf/requests

**Everything in this folder is real.** It was produced by the running DeciTrace platform from the public
GitHub repository [`psf/requests`](https://github.com/psf/requests), collected through the GitHub API. No
discussion, author or link here was invented. The one manual step is labelled below.

| File | What it is | Produced by |
|---|---|---|
| `01_input_thread_issue_7271.json` | The GitHub thread [psf/requests#7271](https://github.com/psf/requests/issues/7271) ("RFC: Adding inline type annotations to Requests"), exactly as the extraction model receives it: each message fenced with its DeciTrace source id, author and role | DeciTrace ingestion + `thread_messages()` |
| `02_extraction_run_qwen2.5-1.5b.json` | The outcome of AI extraction over the five most-discussed threads with **qwen2.5:1.5b** | DeciTrace extraction + evidence validator |
| `03_validated_decision_1.json` | The full decision record for #7271: alternatives, evidence with original GitHub URLs and verification states, validation notes, audit history, and the timeline | Evidence validator, `GET /api/decisions/1`, `GET /api/decisions/1/timeline` |
| `04_answer_qwen2.5-1.5b.json` | The answer to "Why does requests declare type annotations at class level on Response instead of in `__init__`?" with citations | `POST /api/repositories/{id}/ask` with **qwen2.5:1.5b** |

## What happened, honestly

**Extraction (file 02).** `qwen2.5:1.5b` read five real threads in 83 seconds on an 8 GB laptop and proposed five
candidates:
- 3 were **refused** by the validator: their reasons cited no message, or the claimed outcome was not stated by an
  authoritative participant.
- 1 was **malformed**.
- 1 was recorded, as "unresolved" and only partially verified. It had no meaningful topic; after this run we
  changed the rules so that such candidates count as invalid.

No wrong decision got through. The point of this file is to show the validator working, not the model: a 1.5B
model is too small to extract decisions well. Larger open-weight models (Qwen3-8B, the configured default) need
more memory than our test machine had.

**Decision (file 03).** Because the small model could not produce it, the developer wrote the candidate for #7271
by hand from the thread's real comments. It is labelled `created_by: "extractor:manual-ui-check"`. The validator
then checked every citation against the stored comments and decided the status.

The result is **unresolved, with conflicting positions**:
- @edgarrmondragon proposed moving the annotations into `__init__`.
- Maintainer @nateprewitt argued against it ("seems like we're lying about types…").
- He closed with "we're going to defer the patch to requests-cache".

That closing statement contains none of the explicit resolution phrases DeciTrace requires, such as "we decided",
so it is shown as a statement cited as a resolution, not as an approval. A maintainer can confirm the outcome
through human review. This is the intended conservative behaviour: DeciTrace under-claims rather than invents a
decision.

**Answer (file 04).** The model's answer restates the problem and cites decision 1. The backend rates it
**partial**, because the cited decision is unresolved and not explicitly established. The answer contains no
invented link or source.
