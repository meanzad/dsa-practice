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

Content comes from three sources, in descending order of quality:

1. **Wayback Machine** — the original free tutorials, before takeuforward removed them.
2. **`/blogs/data-structure-and-algorithm/...`** — the relaunched site's public
   editorials, with working code in C++/Python/Java/JavaScript.
3. **`/practice/dsa/...`** — statement, examples, constraints and hints, for
   problems with no editorial anywhere.

| | |
|---|---|
| Problems in the sheet | **451** (all of them) |
| **Covered** | **430** |
| — with full solutions and code | **372** |
| — statement only | **58** |
| Still uncovered | **21** |
| Article pages built | **467** |
| Images stored locally | 1,709 (~239 MB) |
| LeetCode / YouTube links | 262 / 378, pointing at the **live** sites |

Article files by source: {'rsc-ref': 288, 'blog': 60, 'live-ssr': 119}

**The two kinds are labelled in the UI.** A solid **Article** pill has the full
write-up and code; a dashed **Statement** pill has the problem only. Editorials
behind the site's login are never fetched.

Three images 404 on takeuforward's own CDN (stale `/draft/` uploads) and are the
only broken images in the archive.

## ⚠️ Keep this repository private

The articles are **takeuforward.org's copyrighted content**. This is a personal
study archive, the same as saving pages for offline reading. Do not publish it,
share the link, or deploy it to a public GitHub Pages site. The generated pages
carry `noindex,nofollow`, but that is not a substitute for keeping the repo private.

## Using the site

Everything under `docs/` is plain HTML/CSS/JS with no build step.

```bash
cd docs && python -m http.server 8000
```

Then open <http://localhost:8000>. (Open `index.html` via `file://` and the browser
will block the `fetch` of `sheet.json` — serve it over HTTP.)

### Syncing progress between machines

Progress and notes live in `localStorage`, which never leaves the browser. To use
the sheet on more than one computer, click **Sync** and paste a GitHub
*fine-grained* token with **Gist** access (read and write) and no other permission.

The token is stored only in that browser and is sent only to `api.github.com`.
**Never commit it.** The first connect creates a private gist; every machine after
that finds the same gist and merges into it.

Merging is per problem, last write wins: two machines editing different problems
both keep their work, and the same problem resolves to the newer edit. The sheet
syncs on load, when you return to the tab, and a moment after each change.

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
  fetch_restored.py gaps       -> data/articles/*.json  (statements, live site)
  blogs.py          extractor for /blogs/ editorials (prose + code)
  fetch_blogs.py    full editorials -> data/articles/*.json (live site)
  fetch_images.py   images     -> docs/assets/img/, rewrites article HTML
  build_site.py     data/      -> docs/
data/               scraped JSON: this is the actual archive
docs/               the generated static site (GitHub Pages serves this folder)
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
python fetch_blogs.py      # full editorials from /blogs/; indexes 442 posts
python fetch_restored.py   # statement-only fallback for what is left
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
- **Blog editorials split prose from code.** The prose is server-rendered into
  `article.editorialContent`, but the code only appears there as a Monaco preview
  with line numbers welded into the text. The clean source is in the flight
  payload under `code_editor`, sometimes inline and sometimes as an RSC reference
  whose row header is *not* newline-anchored (unlike the article pages). Blocks
  are matched to their DOM slot by content, since they are not in document order.
- **Matching problems to blog posts is guarded twice**: a candidate needs both
  string similarity and 55% token overlap, and after fetching, the page's own
  title must still resemble the problem - otherwise the wrong editorial would be
  filed under a problem. Loose matching produced real false positives
  ("Functions (Pass by Reference and Value)" -> `z-function`).
- `fetch_index.py` asserts the parsed totals against the counts shown on the
  archived page (451 / 132 / 183 / 136) and **fails loudly** on a mismatch — a
  silent shortfall would quietly corrupt the archive.
