"""Command line interface: ingest -> extract -> link -> search / pr / evaluate."""
from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from decisionlens import __version__
from decisionlens.codelink import link_decisions
from decisionlens.evaluate import fetch_pep, parse_rejected_ideas, pep_discussion_urls, pep_title, score
from decisionlens.extract import extract_decisions
from decisionlens.identity import accounts_from_dicts, resolve
from decisionlens.ingest import fetch_discourse_thread, load_thread, save_thread
from decisionlens.llm import make_backend
from decisionlens.pr import git_changed_files, parse_diff, render_markdown, surface
from decisionlens.retrieval import DecisionIndex
from decisionlens.store import load_decisions, save_decisions


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _add_backend_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--backend", choices=["ollama", "heuristic"], default="ollama")
    p.add_argument("--model", default="gemma3:1b", help="Ollama model tag (open-weight)")
    p.add_argument("--host", default="http://localhost:11434")


def cmd_ingest(a: argparse.Namespace) -> int:
    thread = fetch_discourse_thread(a.url, max_posts=a.max_posts)
    save_thread(thread, a.out)
    _log(f"saved {len(thread.posts)} posts from '{thread.title}' to {a.out}")
    return 0


def _extract(thread, a) -> list:
    backend = make_backend(a.backend, a.model, a.host)
    return backend, extract_decisions(thread, backend, keep_unverified=a.keep_unverified, progress=_log)


def cmd_extract(a: argparse.Namespace) -> int:
    thread = load_thread(a.thread)
    backend, decisions = _extract(thread, a)
    meta = {"source_thread": thread.url, "title": thread.title, "posts": len(thread.posts), "backend": backend.name}
    save_decisions(a.out, decisions, meta)
    counts = {s: sum(d.status == s for d in decisions) for s in ("accepted", "rejected", "deferred", "open")}
    _log(f"{len(decisions)} decisions {counts} -> {a.out}")
    return 0


def cmd_link(a: argparse.Namespace) -> int:
    decisions, meta = load_decisions(a.decisions)
    link_decisions(decisions, a.repo)
    meta["linked_repo"] = a.repo
    save_decisions(a.out or a.decisions, decisions, meta)
    _log(f"linked {sum(bool(d.code_refs) for d in decisions)}/{len(decisions)} decisions to code")
    return 0


def cmd_search(a: argparse.Namespace) -> int:
    decisions, _ = load_decisions(a.decisions)
    index = DecisionIndex(decisions, prefer=a.embeddings)
    _log(f"retrieval backend: {index.backend}")
    for sim, d in index.search(a.query, k=a.k, status=a.status or ""):
        print(f"{sim:.3f}  [{d.status}] {d.title}  ({d.decision_id})")
        for r in d.reasons[:2]:
            print(f"        reason: {r.text}")
        if d.evidence:
            print(f"        source: {d.evidence[0].url}")
    return 0


def cmd_pr(a: argparse.Namespace) -> int:
    decisions, _ = load_decisions(a.decisions)
    files, symbols = set(a.files or []), set()
    if a.diff:
        with open(a.diff, encoding="utf-8") as fh:
            f, s = parse_diff(fh.read())
        files |= f
        symbols |= s
    if a.repo and a.base and a.head:
        files |= git_changed_files(a.repo, a.base, a.head)
    matches = surface(decisions, sorted(files), sorted(symbols), a.text or "", repo=a.repo, k=a.k, prefer=a.embeddings)
    print(render_markdown(matches))
    return 0


def cmd_identities(a: argparse.Namespace) -> int:
    with open(a.accounts, encoding="utf-8") as fh:
        accounts = accounts_from_dicts(json.load(fh))
    out = [
        {
            "confidence": c.confidence,
            "signals": c.signals,
            "accounts": [f"{m.platform}:{m.handle}" for m in c.members],
        }
        for c in resolve(accounts)
    ]
    print(json.dumps(out, indent=2))
    return 0


def cmd_evaluate(a: argparse.Namespace) -> int:
    pep_text = fetch_pep(a.pep)
    truth = parse_rejected_ideas(pep_text)
    if a.decisions:
        decisions, meta = load_decisions(a.decisions)
        report = score(a.pep, truth, decisions, threshold=a.threshold).to_dict()
        report.update(pep_title=pep_title(pep_text), backend=meta.get("backend"), decisions_file=a.decisions)
        out = json.dumps(report, indent=2)
        if a.out:
            with open(a.out, "w", encoding="utf-8") as fh:
                fh.write(out)
        print(out)
        return 0
    urls = a.thread_url or pep_discussion_urls(pep_text)[: a.max_threads]
    if not urls:
        _log("no discuss.python.org thread found in the PEP headers; pass --thread-url")
        return 2
    _log(f"PEP {a.pep}: {pep_title(pep_text)} | {len(truth)} ground-truth rejected ideas | threads: {urls}")
    all_decisions = []
    backend_name = a.backend
    thread_urls = []
    for url in urls:
        thread = load_thread(a.thread_file) if a.thread_file else fetch_discourse_thread(url, max_posts=a.max_posts)
        _log(f"thread '{thread.title}': {len(thread.posts)} posts (the PEP text is NOT given to the model)")
        backend, decisions = _extract(thread, a)
        backend_name = backend.name
        thread_urls.append(thread.url)
        all_decisions.extend(decisions)
        if a.thread_file:
            break
    report = score(a.pep, truth, all_decisions, threshold=a.threshold).to_dict()
    report["pep_title"] = pep_title(pep_text)
    report["backend"] = backend_name
    report["threads"] = urls
    out = json.dumps(report, indent=2)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(out)
        meta = {"pep": a.pep, "backend": backend_name, "threads": thread_urls}
        if len(thread_urls) == 1:
            meta["source_thread"] = thread_urls[0]
        save_decisions(a.out.replace(".json", "_decisions.json"), all_decisions, meta)
    print(out)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="decisionlens", description=__doc__)
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("ingest", help="download a public Discourse thread")
    s.add_argument("url")
    s.add_argument("-o", "--out", required=True)
    s.add_argument("--max-posts", type=int)
    s.set_defaults(func=cmd_ingest)

    s = sub.add_parser("extract", help="extract decisions from a saved thread")
    s.add_argument("thread")
    s.add_argument("-o", "--out", required=True)
    s.add_argument("--keep-unverified", action="store_true")
    _add_backend_args(s)
    s.set_defaults(func=cmd_extract)

    s = sub.add_parser("link", help="link decisions to source code in a git repository")
    s.add_argument("decisions")
    s.add_argument("--repo", required=True)
    s.add_argument("-o", "--out")
    s.set_defaults(func=cmd_link)

    s = sub.add_parser("search", help="semantic search over decisions")
    s.add_argument("decisions")
    s.add_argument("query")
    s.add_argument("-k", type=int, default=5)
    s.add_argument("--status", choices=["accepted", "rejected", "deferred", "open"])
    s.add_argument("--embeddings", choices=["auto", "dense", "tfidf"], default="auto")
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("pr", help="surface decisions relevant to a pull request")
    s.add_argument("decisions")
    s.add_argument("--repo")
    s.add_argument("--base")
    s.add_argument("--head")
    s.add_argument("--diff", help="unified diff file")
    s.add_argument("--files", nargs="*")
    s.add_argument("--text", help="PR title/description")
    s.add_argument("-k", type=int, default=5)
    s.add_argument("--embeddings", choices=["auto", "dense", "tfidf"], default="auto")
    s.set_defaults(func=cmd_pr)

    s = sub.add_parser("identities", help="resolve contributor identities across platforms")
    s.add_argument("accounts", help="JSON list of {platform, handle, name, email, links}")
    s.set_defaults(func=cmd_identities)

    s = sub.add_parser("evaluate", help="blind evaluation against a Python PEP")
    s.add_argument("--pep", type=int, required=True)
    s.add_argument("--thread-url", action="append")
    s.add_argument("--thread-file", help="use a thread already saved by `ingest` instead of downloading it")
    s.add_argument("--decisions", help="score an existing decisions file instead of running extraction")
    s.add_argument("--max-threads", type=int, default=2)
    s.add_argument("--max-posts", type=int)
    s.add_argument("--threshold", type=float, default=0.2)
    s.add_argument("--keep-unverified", action="store_true")
    s.add_argument("-o", "--out")
    _add_backend_args(s)
    s.set_defaults(func=cmd_evaluate)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
