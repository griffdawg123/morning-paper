# Morning Paper

A personal newspaper for an e-reader. Every morning it reads your feeds, has an
LLM pick and summarise the stories worth your time, fetches their full text,
builds an EPUB, and emails it to your Kindle.

Based on the idea and pipeline of
[jstriblet/kobo-morning-paper](https://github.com/jstriblet/kobo-morning-paper)
(see [Credits](#credits)), reworked for Kindle and for configurable, sectioned
editions built from FreshRSS.

```
gather   FreshRSS categories (+ plain feed URLs) -> new stories from the last day
curate   one LLM call per section: pick, order, one-line blurb, which get full text
extract  trafilatura pulls the article text from the page (truncated feeds don't matter)
build    EPUB: cover, front page (widgets), per-section headlines, article chapters
deliver  email to your @kindle.com address; mark stories read in FreshRSS
```

Nothing breaks the paper for long: a failed widget is left out, a failed LLM
falls back to newest-first with the feed's snippets, an article that can't be
extracted stays a headline with a link.

## Edition layout

- **Cover**: masthead, date, and the lead story of each section.
- **Front page**: widgets (weather, today's calendar, new on Jellyfin, homelab
  status, on this day) and the list of sections.
- **Per section**: a headlines page (every pick with its blurb; full-text picks
  link to their chapter, others to the web), then that section's chapters.
- The Kindle's "Go to" menu is nested by section, and every section and
  article page links back to the contents and on to the next section.

## Configuration

Copy `examples/paper.example.yml` to `paper.yml` and edit it. `${VAR}` is filled
from the environment, which is where secrets go. In flow style (`{...}` or `[...]`) quote it:
`{password: "${X}"}`.

**Sections** map to FreshRSS categories. Add a category in FreshRSS, subscribe
to some feeds, add a section here:

```yaml
sections:
  - name: Gaming
    category: Gaming          # or [Gaming, Nintendo]
    feeds: []                 # extra feeds read directly, no FreshRSS needed
    max_items: 4              # headlines with blurbs
    max_full: 1               # of those, full-text chapters
    hint: Prefer indie and Nintendo news.   # extra guidance for the curator
    days: [sat, sun]          # optional: weekends only
  - name: In the Kitchen
    generate: Suggest three dinners using what's in season in Sydney.  # LLM-written
```

`reader_profile` (a sentence or two about you) is given to the curator for
every section.

**Feeds**: `feeds/starter.opml` is a checked list per category (Australian and
world news, tech, release notes for self-hosted apps, AI, self-hosting, music,
gaming, food, long reads). Import it in FreshRSS (Subscription management >
Import / export) and prune. It also lists tricks for finding feeds: hnrss.org
filters, GitHub `releases.atom`, Substack `/feed`, FreshRSS XPath feeds for sites
without one.

**Widgets** are keyed by name under `widgets:`, rendered in order:

| Widget | Options |
|---|---|
| `weather` | `latitude`, `longitude`, `place` (Open-Meteo, no key) |
| `calendar` | `ical_url` or `ical_urls` (Google: the calendar's secret iCal address) |
| `seerr` | `url`, `email`, `password` (a non-admin user with View Requests), `hours` |
| `kuma` | `url`, `status_page` (slug of a public Uptime Kuma status page), `hours` |
| `on_this_day` | `count` |

Adding one is a function in `src/morning_paper/widgets/` decorated with
`@widget("name", "Heading")` that returns an HTML fragment.

**Notifications**: set `notify.url` to an [ntfy](https://ntfy.sh) topic URL
to get a push when the paper has been sent ("sync your Kindle"), plus one
high-priority alert if the day's run fails after its last retry. Optional:
`token` (ntfy access token), `priority`, `tags`, `click` (URL opened on tap),
`on_failure: false` to skip failure alerts.

**LLM**: any OpenAI-compatible `/chat/completions` endpoint. `models` are tried
in order, so a local model can go first with a hosted fallback. Through Open
WebUI (`base_url: http://<host>:<port>/api`, an API key from Settings >
Account) the model name selects the backend.

## Setup

1. **FreshRSS**: Settings > Authentication > *Allow API access*; then Settings >
   Profile > *API management* > set an API password.
2. **Kindle**: Amazon > Manage Content & Devices > Preferences > Personal
   Document Settings: note the Send-to-Kindle address and add the sending
   address to the *Approved Personal Document E-mail List*.
3. **Gmail**: enable 2-step verification, then create an app password
   (myaccount.google.com/apppasswords).
4. Run it:

```bash
docker run --rm -v $PWD/paper.yml:/config/paper.yml:ro -v $PWD/data:/data \
  -e LLM_API_KEY -e FRESHRSS_API_PASSWORD -e SMTP_USER -e SMTP_PASSWORD -e KINDLE_EMAIL \
  ghcr.io/griffdawg123/morning-paper:latest run --no-send   # build only, look at data/archive/
```

`serve` (the default command) sleeps until `schedule` each day and sends. If it
starts late but before `catch_up_until` and today's paper hasn't run, it runs
straight away. Other commands: `run` (one paper now; `--no-send`, `--section X`,
`--out file.epub`), `widgets` (print the front page, to check config).

State (`state.json`: stories already sent, last run) and an archive of every
edition live in `/data`. Optional fonts go in `/data/fonts`
(`UnifrakturMaguntia-Book.ttf` for a blackletter masthead).

## Development

```bash
python -m venv .venv && .venv/bin/pip install -e '.[test]'
.venv/bin/pytest
```

Pushes to `main` and `v*` tags build `ghcr.io/griffdawg123/morning-paper`.

## Credits

This project exists because of
[kobo-morning-paper](https://github.com/jstriblet/kobo-morning-paper) by
[@jstriblet](https://github.com/jstriblet) (MIT). Its design is the backbone
here: a daily cron pipeline that extracts full article text with trafilatura,
builds a one-chapter-per-article EPUB with ebooklib and a generated cover, and
delivers it to the e-reader, with curation as a separate, pluggable step.

What's different: delivery by Send to Kindle email instead of Calibre-Web Kobo
Sync and KEPUB; stories come from FreshRSS categories mapped to sections rather
than an interest model; curation and blurbs are built in (any OpenAI-compatible
model, with fallback); and a front page of widgets. The code is a fresh
implementation, not a fork.
