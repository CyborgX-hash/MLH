from decisionlens.ingest import fetch_discourse_thread, parse_topic_url
from decisionlens.text import chunk_posts, clean_html, sentences
from decisionlens.models import Post


def test_clean_html_drops_quotes_and_keeps_code():
    html = (
        '<aside class="quote"><blockquote>old quoted text</blockquote></aside>'
        "<p>My reply with <code>foo_bar()</code> and a <a href='x'>link</a>.</p>"
    )
    text = clean_html(html)
    assert "old quoted text" not in text
    assert "foo_bar()" in text and "link" in text


def test_sentences_ignores_fragments():
    assert sentences("Hi. This is a real sentence. Ok") == ["This is a real sentence."]


def test_chunking_respects_budget():
    posts = [Post(i, "u", "", "x" * 1000, "") for i in range(10)]
    chunks = chunk_posts(posts, max_chars=3000)
    assert all(len(c) <= 3 for c in chunks)
    assert sum(len(c) for c in chunks) == 10


def test_parse_topic_url_variants():
    assert parse_topic_url("https://d.org/t/my-slug/123")[1:] == ("my-slug", 123)
    assert parse_topic_url("https://d.org/t/my-slug/123/45")[1:] == ("my-slug", 123)
    assert parse_topic_url("https://d.org/t/123/45")[2] == 123


def test_fetch_discourse_thread_pages_through_stream():
    def raw(i):
        return {"id": i * 10, "post_number": i, "username": f"u{i}", "created_at": "t", "cooked": f"<p>post {i}</p>", "post_type": 1}

    def fake(url):
        if url.endswith("/t/7.json"):
            return {"slug": "s", "title": "T", "post_stream": {"stream": [10, 20, 30], "posts": [raw(1)]}}
        assert "post_ids[]=20" in url and "post_ids[]=30" in url
        return {"post_stream": {"posts": [raw(2), raw(3)]}}

    thread = fetch_discourse_thread("https://d.org/t/s/7", fetcher=fake, delay=0)
    assert [p.post_id for p in thread.posts] == [1, 2, 3]
    assert thread.posts[2].url == "https://d.org/t/s/7/3"
    assert thread.posts[0].text == "post 1"
