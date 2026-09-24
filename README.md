# Striver's A2Z DSA Sheet — personal offline archive

A private, self-contained copy of the Striver A2Z DSA sheet and its tutorial
articles, rebuilt from the Wayback Machine.

## Why this exists

takeuforward.org was redesigned. The old free tutorial articles were removed —
`https://takeuforward.org/data-structure/trapping-rainwater/` and its siblings now
return **404**, and the replacement `/plus/...` pages sit behind an account. The
content survives only in the Internet Archive.

This repo scrapes those archived pages once and rebuilds a static site with the
same structure: all **451 problems** across 18 categories, their articles, and a
progress tracker that needs no login.

## What was recovered

Content comes from two sources. takeuforward later restored much of the sheet at
`/prep-hub/strivers-a2z-dsa-sheet`, so gaps the archive could not fill were topped
up from the live site.

| | |
|---|---|
| Problems in the sheet | **451** (all of them) |
| **Covered** | **429** |
| — full articles, with solutions and code (Wayback) | **309** |
| — problem statements only (live site) | **120** |
| Still uncovered | **22** |
| Article pages built | **407** |
| Images stored locally | ~1,473 (~225 MB) |
| LeetCode / YouTube links | 262 / 378, pointing at the **live** sites |

**The two kinds are labelled in the UI.** A solid **Article** pill is a full
archived tutorial: problem statement, intuition, complexity analysis and code in
C++/Java/Python/JavaScript. A dashed **Statement** pill is a page recovered from
the relaunched site: statement, examples, constraints and hints, but **no
solution** — the new site keeps its editorials behind a login, which this scraper
does not attempt to bypass.

The remaining 22 have no article anywhere: some never had one, some were never
captured by the Wayback Machine, and a few were dropped or renamed in the relaunch.

## ⚠️ Keep this repository private

The articles are **takeuforward.org's copyrighted content**. This is a personal
study archive, the same as saving pages for offline reading. Do not publish it,
share the link, or deploy it to a public GitHub Pages site. The generated pages
carry `noindex,nofollow`, but that is not a substitute for keeping the repo private.

## Using the site

Everything under `site/` is plain HTML/CSS/JS with no build step.

```bash
cd site && python -m http.server 8000
```

Then open <http://localhost:8000>. (Open `index.html` via `file://` and the browser
will block the `fetch` of `sheet.json` — serve it over HTTP.)

For GitHub Pages on a **private** repo, point Pages at the `site/` folder.

**Features**
- All 451 problems, grouped by category and subcategory, with solved counts per section
- Overall and per-difficulty progress (Easy / Medium / Hard)
- Search, plus filters for difficulty, solved/unsolved, and revision
- A star per problem to mark it for revision
- Archived article pages with **C++ / Java / Python / JavaScript tabs**, a copy
  button, and locally stored images — your language choice is remembered everywhere
- **YouTube and LeetCode links point at the live sites**, never the archived copies

**Progress** is stored in your browser's `localStorage` under `a2z-progress-v1`.
It does not sync between browsers or machines — use **Export progress** to save a
JSON backup and **Import** to restore it. Clearing site data erases it, so export
occasionally.

## Repo layout

```
scrape/
  common.py         Wayback fetching, caching, throttling, RSC payload parsing
  fetch_index.py    the sheet -> data/sheet.json  (with an integrity check)
  fetch_articles.py articles   -> data/articles/*.json
  fetch_restored.py gaps       -> data/articles/*.json  (from the relaunched live site)
  fetch_images.py   images     -> site/assets/img/, rewrites article HTML
  build_site.py     data/      -> site/
data/               scraped JSON: this is the actual archive
site/               the generated static site
.cache/             raw HTTP responses (gitignored); makes re-runs free
```

### Windows: long paths

Article filenames are descriptive and the repo may sit in a deep folder, which can
trip Windows' 260-character path limit (`Filename too long` on `git add`). If that
happens:

```bash
git config core.longpaths true
```

## Re-running the scrape

Order matters. Every step is resumable — `.cache/` holds raw responses and
already-scraped articles are skipped, so an interrupted run costs nothing.

```bash
cd scrape
python fetch_index.py      # fast
python fetch_articles.py   # slow: hundreds of throttled requests
python fetch_restored.py   # fills gaps from the live site; fast
python fetch_images.py     # moderate; pulls from the live CDN
python build_site.py       # fast
```

Rebuilding the site only needs `build_site.py`.

### Notes on the scrape

- **The content is not in the rendered HTML.** takeuforward is a Next.js App Router
  site; article bodies live in the RSC flight payload (`self.__next_f`) and never
  reach the archived DOM. Scraping visible HTML yields empty pages. `common.py`
  parses the payload instead, and `"content":"$1b"` is resolved as a reference to a
  `1b:T<hexlen>,` text row — whose length is a **UTF-8 byte count**, not characters.
- **The archive rate-limits hard.** Requests are serial, throttled, and share one
  keep-alive session; a fresh TLS connection per request triggers `ConnectionError`
  far more often than the rate limiter does.
- **Some articles were never archived.** They are listed in `data/report.json`, and
  those problems render with the Article link disabled rather than broken.
- `fetch_index.py` asserts the parsed totals against the counts shown on the
  archived page (451 / 132 / 183 / 136) and **fails loudly** on a mismatch — a
  silent shortfall would quietly corrupt the archive.
