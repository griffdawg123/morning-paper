"""Edition -> EPUB.

Layout: cover, front page (widgets), then for each section a headlines page
(every pick with its blurb; full-text picks link to their chapter, the rest
to the web) followed by that section's article chapters. The table of contents
is nested by section, so the Kindle's "Go to" menu works like a paper's index.
Every section and article page also links back to the front page's contents
list (front.xhtml#contents) and on to the next section, so you can jump around
without the Kindle menu.
Kept deliberately plain (no images, minimal CSS): Send to Kindle converts the
EPUB and fancy layout doesn't survive.
"""

from __future__ import annotations

import io
import uuid
from pathlib import Path

from ebooklib import epub
from PIL import Image, ImageDraw, ImageFont

from .models import Edition
from .text import esc

CSS = """
body { font-family: serif; line-height: 1.45; }
h1 { font-size: 1.5em; margin: 0 0 0.3em; }
h2 { font-size: 1.2em; margin: 1.2em 0 0.3em; border-bottom: 1px solid #000; }
h3 { font-size: 1.05em; margin: 1em 0 0.2em; }
p { margin: 0 0 0.7em; }
.meta { font-size: 0.85em; font-style: italic; margin-bottom: 1.2em; }
.blurb { margin: 0 0 0.2em; }
.src { font-size: 0.8em; margin: 0 0 1em; }
.masthead { text-align: center; }
.masthead .tagline { font-style: italic; font-size: 0.9em; }
.nav { font-size: 0.85em; margin-top: 2em; }
.nav-top { font-size: 0.85em; margin: 0 0 0.6em; }
"""

CONTENTS = "front.xhtml#contents"  # the front page's section list

FONT_DIRS = ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/TTF", "/usr/share/fonts/dejavu"]


def _font(names: list[str], size: int, font_dir: str | None = None):
    for d in ([font_dir] if font_dir else []) + FONT_DIRS:
        for n in names:
            p = Path(d) / n
            if p.is_file():
                return ImageFont.truetype(str(p), size)
    return ImageFont.load_default(size=size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, width: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def cover_image(ed: Edition, font_dir: str | None = None) -> bytes:
    """A newspaper-ish grayscale cover: masthead, date, top headlines."""
    W, H, M = 1236, 1648, 80
    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)
    serif_b = ["DejaVuSerif-Bold.ttf", "PTSerif-Bold.ttf"]
    serif = ["DejaVuSerif.ttf", "PTSerif-Regular.ttf"]
    masthead = _font(["UnifrakturMaguntia-Book.ttf"] + serif_b, 110, font_dir)
    y = M
    for line in _wrap(d, ed.title, masthead, W - 2 * M):
        d.text((W / 2, y), line, font=masthead, fill=0, anchor="ma")
        y += 130
    small = _font(serif, 34, font_dir)
    y += 10
    d.line((M, y, W - M, y), fill=0, width=4)
    y += 18
    d.text((M, y), ed.date.strftime("%A %-d %B %Y"), font=small, fill=0)
    d.text((W - M, y), ed.tagline, font=small, fill=0, anchor="ra")
    y += 56
    d.line((M, y, W - M, y), fill=0, width=2)
    y += 50

    head = _font(serif_b, 52, font_dir)
    body = _font(serif, 34, font_dir)
    label = _font(serif_b, 28, font_dir)
    for section in ed.sections:
        if not section.items or y > H - 300:
            continue
        top = section.items[0]
        d.text((M, y), section.name.upper(), font=label, fill=0)
        y += 44
        for line in _wrap(d, top.title, head, W - 2 * M)[:3]:
            d.text((M, y), line, font=head, fill=0)
            y += 62
        blurb = _wrap(d, top.blurb, body, W - 2 * M)
        if len(blurb) > 3:
            blurb = blurb[:3]
            blurb[-1] = blurb[-1].rsplit(" ", 1)[0] + " …"
        for line in blurb:
            d.text((M, y), line, font=body, fill=0)
            y += 44
        y += 40
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _page(title: str, file_name: str, body: str, css: epub.EpubItem) -> epub.EpubHtml:
    page = epub.EpubHtml(title=title, file_name=file_name, lang="en")
    page.content = body
    page.add_item(css)
    return page


def build(ed: Edition, out_path: Path, font_dir: str | None = None) -> Path:
    book = epub.EpubBook()
    book.set_identifier(f"urn:uuid:{uuid.uuid4()}")
    title = f"{ed.title}: {ed.date:%a %-d %b %Y}"
    book.set_title(title)
    book.set_language("en")
    book.add_author(ed.title)
    book.set_cover("cover.jpg", cover_image(ed, font_dir), create_page=True)

    css = epub.EpubItem(uid="style", file_name="style.css", media_type="text/css", content=CSS)
    book.add_item(css)

    spine: list = ["cover"]
    toc: list = []

    # Front page: masthead, contents, widgets.
    contents = "".join(
        f'<li><a href="sec-{n}.xhtml">{esc(s.name)}</a></li>'
        for n, s in enumerate(ed.sections)
    )
    widgets = "".join(f"<h2>{esc(h)}</h2>{html}" for h, html in ed.front_page)
    front = _page(
        "Front page",
        "front.xhtml",
        f'<div class="masthead"><h1>{esc(ed.title)}</h1>'
        f'<p class="tagline">{esc(ed.tagline)}</p><p>{ed.date:%A %-d %B %Y}</p></div>'
        f'{widgets}<h2 id="contents">In this edition</h2><ul>{contents}</ul>',
        css,
    )
    book.add_item(front)
    spine.append(front)
    toc.append(epub.Link("front.xhtml", "Front page", "front"))

    home = f'<a href="{CONTENTS}">Contents</a>'
    for n, section in enumerate(ed.sections):
        sec_file = f"sec-{n}.xhtml"
        nxt = ed.sections[n + 1].name if n + 1 < len(ed.sections) else None
        next_link = f' · <a href="sec-{n + 1}.xhtml">Next: {esc(nxt)}</a>' if nxt else ""
        parts = [f'<p class="nav-top">{home}{next_link}</p>', f"<h1>{esc(section.name)}</h1>"]
        if section.generated_html:
            parts.append(section.generated_html)
        chapters = []
        for m, item in enumerate(section.items):
            art_file = f"art-{n}-{m}.xhtml"
            if item.full and item.body_html:
                link = f'<a href="{art_file}">{esc(item.title)}</a>'
                mins = max(1, round(item.words / 230))
                src = f"{esc(item.source)} · {mins} min read"
            else:
                link = f'<a href="{esc(item.url)}">{esc(item.title)}</a>'
                src = f"{esc(item.source)} · on the web"
            parts.append(f"<h3>{link}</h3><p class=\"blurb\">{esc(item.blurb)}</p><p class=\"src\">{src}</p>")
            if item.full and item.body_html:
                byline = " · ".join(x for x in (esc(item.source), esc(item.author)) if x)
                art = _page(
                    item.title,
                    art_file,
                    f"<h1>{esc(item.title)}</h1><p class=\"meta\">{byline}</p>"
                    f"{item.body_html}"
                    f'<p class="nav">Original: {esc(item.url)}<br/>'
                    f'<a href="{sec_file}">Back to {esc(section.name)}</a> · {home}{next_link}</p>',
                    css,
                )
                chapters.append(art)
        parts.append(f'<p class="nav">{home}{next_link}</p>')
        page = _page(section.name, sec_file, "".join(parts), css)
        book.add_item(page)
        spine.append(page)
        for art in chapters:
            book.add_item(art)
            spine.append(art)
        sec_link = epub.Section(section.name, sec_file)
        toc.append((sec_link, [epub.Link(a.file_name, a.title, a.file_name) for a in chapters]) if chapters else epub.Link(sec_file, section.name, sec_file))

    book.toc = toc
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = spine
    out_path.parent.mkdir(parents=True, exist_ok=True)
    epub.write_epub(str(out_path), book)
    return out_path
