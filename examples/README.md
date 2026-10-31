# Examples: real input and real output

There are two sets of examples, both produced by running the code on real public data:

- **[`decitrace/`](decitrace/README.md): the DeciTrace web platform** on the GitHub repository `psf/requests`
  (thread input, AI extraction outcome, validated decision with evidence, cited answer).
- **The files below: the `decisionlens` PEP evaluation engine** on the discuss.python.org thread for PEP 695
  (the hackathon's evaluation scenario).

## PEP evaluation engine

Everything here was produced by running the tool. Nothing was written by hand except
`identity_accounts.json`, which is a representative input for the identity resolver.
CI (`scripts/validate_examples.py`) checks that every quote cited in the decision files
really occurs in the post it cites.

## Input

| File | What it is |
|---|---|
| `sample_input.json` | The public discuss.python.org thread [PEP 695: Type Parameter Syntax](https://discuss.python.org/t/pep-695-type-parameter-syntax/21646), 140 posts, downloaded with `decisionlens ingest`. |
| `identity_accounts.json` | Contributor accounts across GitHub, Discourse and a mailing list. |

## Output

| File | Command | Produced by |
|---|---|---|
| `sample_output.json` | `decisionlens extract sample_input.json -o sample_output.json --model gemma3:1b` | gemma3:1b via Ollama |
| `pep695_eval_gemma3-1b.json` | `decisionlens evaluate --pep 695 --decisions sample_output.json` | scorer only |
| `pep695_qwen2.5-1.5b_decisions.json` | `decisionlens extract sample_input.json -o pep695_qwen2.5-1.5b_decisions.json --model qwen2.5:1.5b` | qwen2.5:1.5b via Ollama |
| `pep695_eval_qwen2.5-1.5b.json` | `decisionlens evaluate --pep 695 --decisions pep695_qwen2.5-1.5b_decisions.json` | scorer only |
| `pep695_eval_heuristic.json`, `pep695_eval_heuristic_decisions.json` | `decisionlens evaluate --pep 695 --backend heuristic --thread-file sample_input.json` | rule-based fallback, no model |
| `search_output.txt` | `decisionlens search sample_output.json "why not declare variance explicitly" -k 3 --embeddings tfidf` | TF-IDF retrieval |
| `pr_check_output.md` | `decisionlens pr sample_output.json --files Objects/typevarobject.c --text "Add explicit variance keywords to type parameter syntax" -k 3 --embeddings tfidf` | TF-IDF retrieval |
| `identity_output.json` | `decisionlens identities identity_accounts.json` | rule-based resolver |

## Blind PEP 695 evaluation

The extractor saw only the discussion. PEP 695's "Rejected Ideas" section lists five ideas: Prefix Clause,
Angle Brackets, Bounds Syntax, Explicit Variance and Name Mangling.

| Backend | Decisions | Predicted rejected | Recovered (scorer) | Recovered (checked by hand) |
|---|---|---|---|---|
| gemma3:1b | 62 | 7 | 0 / 5 | 0 / 5 |
| qwen2.5:1.5b | 21 | 2 | 1 / 5 | 1 / 5 (Prefix Clause, as "Decorator-based Syntax") |
| heuristic (no model) | 39 | 14 | 2 / 5 | 1 / 5 |

**Reading these numbers honestly**

- **gemma3:1b found no rejected idea from the PEP.** It labelled 50 of 62 decisions "accepted" and its
  "rejected" items are mostly side remarks. A 1B model is too small for this task. The pipeline accepts any
  Ollama model, and testing a larger one is the next step.
- **qwen2.5:1.5b is more conservative and more precise.** It produced 21 decisions, only 2 rejected, and one of
  them is a genuine recovery: the decorator-based syntax that the PEP rejects under "Prefix Clause". Both runs
  took about 4.5 minutes on a laptop CPU.
- **The heuristic's second match is a false positive.** "Prefix Clause" is a real recovery (a post states
  "This idea was rejected because such forms would be confused with regular decorators"), but the match
  for "Explicit Variance" is a decorator-syntax remark that only shares words with it.
- The scorer is lexical, so it can both miss paraphrased recoveries and accept word-overlap coincidences.
  Matches should be reviewed by hand, as above.

## What the other outputs show

- `search_output.txt` and `pr_check_output.md`: retrieval works and every result links to the original post.
  The quality of what they surface is limited by the 1B extraction above. For example, the top "rejected"
  variance result cites a post that is not actually a rejection.
- `identity_output.json`: `github:jdoe`, `discourse:jane_d` and `mailing-list:j.doe` are merged (shared email
  plus an explicit link, confidence 0.98). `github:bobby` and `discourse:bobroe` are merged through an explicit
  link. `discourse:bob_roe` stays separate: a matching handle and name alone (0.6) are below the 0.7 merge bar.
