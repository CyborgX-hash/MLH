"""CI check: every committed example output must be valid and every claim must be traceable.

For each examples/*decisions*.json the cited quotes must really occur in the example input thread
named in its metadata, so a hand-edited or hallucinated example fails CI.
"""
import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def norm(text):
    return re.sub(r"\s+", " ", re.sub(r"[`*_\"'“”‘’]", "", text)).strip().lower()


def main():
    thread = json.loads((ROOT / "examples" / "sample_input.json").read_text())
    posts = {p["post_id"]: norm(p["text"]) for p in thread["posts"]}
    files = sorted(
        set(glob.glob(str(ROOT / "examples" / "sample_output.json")))
        | set(glob.glob(str(ROOT / "examples" / "*_decisions.json")))
    )
    errors = []
    for f in files:
        data = json.loads(Path(f).read_text())
        if not f.endswith("sample_output.json") and data["meta"].get("source_thread") != thread["url"]:
            print(f"skip {Path(f).name}: built from a different thread than sample_input.json")
            continue
        decisions = data["decisions"]
        if not decisions:
            errors.append(f"{f}: no decisions")
        if data["meta"].get("source_thread") != thread["url"]:
            errors.append(f"{f}: meta.source_thread does not match sample_input.json")
        for d in decisions:
            if d["status"] not in ("accepted", "rejected", "deferred", "open"):
                errors.append(f"{d['decision_id']}: bad status {d['status']}")
            spans = list(d["evidence"]) + [e for r in d["reasons"] for e in r["evidence"]]
            if not spans:
                errors.append(f"{d['decision_id']}: no evidence")
            for e in spans:
                if e["post_id"] not in posts:
                    errors.append(f"{d['decision_id']}: cites unknown post {e['post_id']}")
                elif norm(e["quote"]) not in posts[e["post_id"]]:
                    errors.append(f"{d['decision_id']}: quote not found in post {e['post_id']}")
    for e in errors:
        print("FAIL", e)
    if errors:
        return 1
    print(f"OK: {len(files)} example output file(s) validated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
