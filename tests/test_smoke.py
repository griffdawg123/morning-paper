"""Offline tests: config, JSON parsing, HTML cleaning, curation fallback, EPUB build."""

from __future__ import annotations

import zipfile
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from morning_paper import config, curate, epub
from morning_paper.llm import LLM, LLMError, parse_json
from morning_paper.models import Edition, Item, Section
from morning_paper.text import clean_html, to_text, word_count


def test_config_env_and_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("KINDLE_EMAIL", "me@kindle.com")
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    p = tmp_path / "paper.yml"
    p.write_text(
        'delivery: {to: ["${KINDLE_EMAIL}", "${UNSET_VAR}"], smtp_password: "${SMTP_PASSWORD}"}\n'
        "sections:\n  - {name: News, category: News}\n  - {name: Mixed, category: [A, B]}\n"
    )
    cfg = config.load(p)
    assert cfg["delivery"]["to"] == ["me@kindle.com"]
    assert cfg["delivery"]["smtp_password"] == ""
    assert cfg["delivery"]["smtp_host"] == "smtp.gmail.com"
    assert cfg["sections"][0]["category"] == ["News"]
    assert cfg["sections"][1]["category"] == ["A", "B"]
    assert cfg["sections"][0]["max_items"] == 6


def test_example_config_loads(monkeypatch):
    from pathlib import Path

    cfg = config.load(Path(__file__).parent.parent / "examples" / "paper.example.yml")
    assert [s["name"] for s in cfg["sections"]][0] == "News"
    assert "weather" in cfg["widgets"]


@pytest.mark.parametrize(
    "reply",
    [
        '{"picks": [{"id": 1}]}',
        'Sure!\n```json\n{"picks": [{"id": 1}]}\n```',
        '<think>hmm {"no": 1}</think>{"picks": [{"id": 1}]}',
    ],
)
def test_parse_json(reply):
    assert parse_json(reply)["picks"][0]["id"] == 1


def test_parse_json_rejects_prose():
    with pytest.raises(LLMError):
        parse_json("I could not decide.")


def test_clean_html_strips_junk():
    dirty = (
        '<div class="x" style="color:red"><script>alert(1)</script><p onclick="x">Hi <b>there</b></p>'
        '<img src="a.png"><a href="javascript:x">bad</a> <a href="https://ok">ok</a><custom>tag</custom></div>'
    )
    out = clean_html(dirty)
    assert "script" not in out and "onclick" not in out and "style" not in out and "<img" not in out
    assert 'href="https://ok"' in out and "javascript" not in out
    assert "<custom" not in out and "tag" in out
    assert to_text(out).startswith("Hi there")


def _items(n: int) -> list[Item]:
    now = datetime.now(timezone.utc)
    return [
        Item(id=f"u{i}", url=f"https://example.com/{i}", title=f"Story {i}", source="Ex",
             published=now - timedelta(hours=i), snippet=f"Snippet {i}")
        for i in range(n)
    ]


def test_curate_without_llm_falls_back_to_newest():
    llm = LLM("", "", [])
    picks = curate.curate_section(llm, {"name": "S", "max_items": 3, "max_full": 1, "hint": ""}, _items(5), "")
    assert [p.title for p in picks] == ["Story 0", "Story 1", "Story 2"]
    assert [p.full for p in picks] == [True, False, False]
    assert picks[0].blurb == "Snippet 0"


def test_curate_uses_llm_picks(monkeypatch):
    llm = LLM("http://llm", "", ["m"])
    monkeypatch.setattr(llm, "chat", lambda *a, **k: '{"picks": [{"id": 2, "blurb": "B2", "full": true}, '
                        '{"id": 2}, {"id": 99}, {"id": 0, "blurb": "B0", "full": true}]}')
    picks = curate.curate_section(llm, {"name": "S", "max_items": 3, "max_full": 1, "hint": ""}, _items(4), "")
    assert [p.title for p in picks] == ["Story 2", "Story 0"]  # dup + out-of-range dropped
    assert [p.full for p in picks] == [True, False]  # max_full enforced
    assert picks[0].blurb == "B2"


def test_epub_builds(tmp_path):
    items = _items(3)
    items[0].full, items[0].body_html, items[0].words = True, "<p>" + "word " * 300 + "</p>", 300
    for it in items:
        it.blurb = f"About {it.title} & <friends>"
    ed = Edition(
        title="Test Paper",
        tagline="Tagline",
        date=datetime(2026, 11, 25, 6, tzinfo=ZoneInfo("Australia/Sydney")),
        front_page=[("Weather", "<p>Sunny</p>")],
        sections=[Section("News", items), Section("Kitchen", [], generated_html="<h2>Tacos</h2><p>Yes.</p>")],
    )
    out = epub.build(ed, tmp_path / "p.epub")
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        assert "EPUB/art-0-0.xhtml" in names and "EPUB/art-0-1.xhtml" not in names
        sec = z.read("EPUB/sec-0.xhtml").decode()
        assert 'href="art-0-0.xhtml"' in sec and "https://example.com/1" in sec
        assert "&amp; &lt;friends&gt;" in sec
        assert "Tacos" in z.read("EPUB/sec-1.xhtml").decode()
        # Navigation: contents anchor on the front page, links back to it everywhere.
        assert 'id="contents"' in z.read("EPUB/front.xhtml").decode()
        assert 'href="front.xhtml#contents"' in sec and 'href="sec-1.xhtml"' in sec
        last = z.read("EPUB/sec-1.xhtml").decode()
        assert 'href="front.xhtml#contents"' in last and "Next:" not in last
        art = z.read("EPUB/art-0-0.xhtml").decode()
        assert 'href="sec-0.xhtml"' in art and 'href="front.xhtml#contents"' in art and 'href="sec-1.xhtml"' in art
        assert any(n.endswith("cover.jpg") for n in names)
    assert word_count("<p>one two three</p>") == 3


def test_notify_posts_to_ntfy(monkeypatch):
    from morning_paper import notify

    calls = []
    monkeypatch.setattr(notify.requests, "post", lambda url, data, headers, timeout: calls.append((url, data, headers)) or _Ok())
    cfg = {"title": "Paper", "notify": {"url": "http://ntfy/topic", "token": "t"}}
    notify.published(cfg, "Paper: Wed", 3, 12, 4)
    url, data, headers = calls[0]
    assert url == "http://ntfy/topic" and b"12 stories in 3 sections" in data
    assert headers["Title"] == "Paper is out" and headers["Authorization"] == "Bearer t"
    notify.failed(cfg, "boom")
    assert calls[1][2]["Priority"] == "high" and b"boom" in calls[1][1]
    notify.published({"title": "Paper", "notify": {"url": ""}}, "x", 1, 1, 1)
    assert len(calls) == 2  # unconfigured: no request


class _Ok:
    def raise_for_status(self):
        pass


def test_season_by_hemisphere():
    assert curate.season(11, "south") == "spring"
    assert curate.season(11, "north") == "autumn"
    assert curate.season(1, "south") == "summer"


def test_generate_section_tidies_markdown(monkeypatch):
    llm = LLM("http://llm", "", ["m"])
    monkeypatch.setattr(llm, "chat", lambda *a, **k: "# In the Kitchen\n# Ideas\nTry these:\n* One\n* Two\n")
    html = curate.generate_section(llm, {"name": "In the Kitchen", "generate": "x"}, datetime(2026, 11, 24), "")
    assert "In the Kitchen" not in html and "<h2>Ideas</h2>" in html and "<h1>" not in html
    assert "<li>One</li>" in html


def test_empty_paper_is_not_sent(tmp_path, monkeypatch):
    from morning_paper import deliver, pipeline

    p = tmp_path / "paper.yml"
    p.write_text(f"data_dir: {tmp_path}\ndelivery: {{smtp_user: u, smtp_password: p, to: [k@kindle.com]}}\n")
    sent = []
    monkeypatch.setattr(deliver, "send", lambda *a: sent.append(a))
    with pytest.raises(pipeline.EmptyPaper):
        pipeline.run(config.load(p))
    assert not sent
    assert not (tmp_path / "state.json").exists()  # not counted as today's run


@pytest.mark.parametrize(
    "title,source,want",
    [
        ("v3.3.5", "Release notes from immich", "immich v3.3.5"),
        ("10.11.3", "Release notes from jellyfin", "jellyfin 10.11.3"),
        ("FreshRSS 1.31.0", "Release notes from FreshRSS", "FreshRSS 1.31.0"),
        ("Molly Meldrum dies", "Music Feeds", "Molly Meldrum dies"),
    ],
)
def test_display_title(title, source, want):
    from morning_paper.sources import display_title

    assert display_title(title, source) == want
