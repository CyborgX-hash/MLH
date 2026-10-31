"""Collect public discussions. Read-only: nothing is ever posted back to a project."""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple

from decisionlens.models import Post, Thread
from decisionlens.text import clean_html

USER_AGENT = "decisionlens-hackathon/0.1 (read-only research tool)"
Fetcher = Callable[[str], Any]


def http_get(url: str, as_json: bool = True, retries: int = 4, timeout: int = 30) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8")
            return json.loads(body) if as_json else body
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < retries - 1:
                time.sleep(float(exc.headers.get("Retry-After", 2 * (attempt + 1))))
                continue
            raise
        except urllib.error.URLError:
            if attempt == retries - 1:
                raise
            time.sleep(1 + attempt)
    raise RuntimeError("unreachable")


def parse_topic_url(url: str) -> Tuple[str, str, int]:
    m = re.match(r"(https?://[^/]+)/t/([^?#]+)", url)
    if not m:
        raise ValueError(f"not a Discourse topic URL: {url}")
    parts = [p for p in m.group(2).split("/") if p]
    if parts and parts[0].isdigit():  # /t/<id>[/<post>]
        return m.group(1), "topic", int(parts[0])
    if len(parts) >= 2 and parts[1].isdigit():  # /t/<slug>/<id>[/<post>]
        return m.group(1), parts[0], int(parts[1])
    raise ValueError(f"not a Discourse topic URL: {url}")


def topic_key(url: str) -> Tuple[str, int]:
    base, _, topic_id = parse_topic_url(url)
    return base, topic_id


def _to_post(raw: Dict[str, Any], base: str, slug: str, topic_id: int) -> Post:
    n = raw["post_number"]
    return Post(
        post_id=n,
        author=raw.get("username") or "unknown",
        created_at=raw.get("created_at", ""),
        text=clean_html(raw.get("cooked", "")),
        url=f"{base}/t/{slug}/{topic_id}/{n}",
        reply_to=raw.get("reply_to_post_number"),
    )


def fetch_discourse_thread(
    url: str,
    max_posts: Optional[int] = None,
    fetcher: Fetcher = http_get,
    delay: float = 0.3,
) -> Thread:
    base, slug, topic_id = parse_topic_url(url)
    topic = fetcher(f"{base}/t/{topic_id}.json")
    slug = topic.get("slug", slug)
    stream: List[int] = list(topic["post_stream"]["stream"])
    raw_posts = {p["id"]: p for p in topic["post_stream"]["posts"]}

    missing = [i for i in stream if i not in raw_posts]
    if max_posts:
        stream = stream[:max_posts]
        missing = [i for i in missing if i in stream]
    for i in range(0, len(missing), 20):
        batch = missing[i : i + 20]
        query = "&".join(f"post_ids[]={pid}" for pid in batch)
        data = fetcher(f"{base}/t/{topic_id}/posts.json?{query}")
        for p in data["post_stream"]["posts"]:
            raw_posts[p["id"]] = p
        time.sleep(delay)

    posts = []
    for pid in stream:
        raw = raw_posts.get(pid)
        if not raw or raw.get("post_type", 1) != 1 or raw.get("hidden"):
            continue
        post = _to_post(raw, base, slug, topic_id)
        if post.text:
            posts.append(post)
    return Thread(
        source="discourse",
        url=f"{base}/t/{slug}/{topic_id}",
        title=topic.get("title", slug),
        posts=posts,
    )


def load_thread(path: str) -> Thread:
    with open(path, encoding="utf-8") as fh:
        return Thread.from_dict(json.load(fh))


def save_thread(thread: Thread, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(thread.to_dict(), fh, indent=2, ensure_ascii=False)
