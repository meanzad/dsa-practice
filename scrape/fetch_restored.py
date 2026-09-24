"""Fill gaps from the relaunched live site.

takeuforward brought most of the sheet back at /prep-hub/strivers-a2z-dsa-sheet.
The new pages are server-rendered, so no RSC payload parsing is needed here:
`<main>` holds the content.

Two public page families are used:
  /learning/dsa/<slug>  - full tutorial articles
  /practice/dsa/<slug>  - problem statement, examples, constraints, hints
The `?tab=solution` editorials are behind a login and are NOT fetched.

Only problems that still lack an article are touched; existing archived
articles are left alone.
"""
import difflib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bs4 import BeautifulSoup, Comment
from common import DATA, http_get, slugify
from fetch_index import extract_array
from common import flight_payload

SHEET_URL = "https://takeuforward.org/prep-hub/strivers-a2z-dsa-sheet"
BASE = "https://takeuforward.org"

# Chrome that the SSR'd page carries but that means nothing offline.
NOISE = re.compile(
    r"advertisement|log ?in ?/ ?sign ?up|log in or sign up|see plans and pricing"
    r"|early bird offer|sale ends?|claim|subscribe|upgrade to", re.I)


def norm(s: str) -> str:
    s = s.lower().replace("&", "and")
    s = re.sub(r"\(.*?\)", "", s)
    # Old titles often carry a "| Check if ..." style suffix the new sheet drops.
    s = s.split("|")[0]
    return re.sub(r"[^a-z0-9]+", "", s)


def load_outline():
    html = http_get(SHEET_URL, throttle=False)
    if not html:
        raise SystemExit("could not fetch the new sheet page")
    nodes = extract_array(flight_payload(html), '"nodes":[')
    out = []

    def walk(ns):
        for n in ns:
            if n.get("kind") == "problem" and isinstance(n.get("href"), str):
                out.append(n)
            walk(n.get("children") or [])

    walk(nodes)
    return out


def clean_main(html: str):
    soup = BeautifulSoup(html, "lxml")
    main = soup.find("main")
    if main is None:
        return None
    for t in main.find_all(["script", "style", "noscript", "iframe", "svg",
                            "input", "textarea", "form"]):
        t.decompose()
    for c in main.find_all(string=lambda x: isinstance(x, Comment)):
        c.extract()
    # Interactive widgets (quiz, code editor, submit) cannot work offline.
    for b in main.find_all("button"):
        b.decompose()
    for el in main.find_all(["div", "section", "aside", "p", "span"]):
        txt = el.get_text(" ", strip=True)
        if txt and len(txt) < 120 and NOISE.search(txt):
            el.decompose()
    for a in main.find_all("a", href=True):
        h = a["href"]
        if h.startswith("/"):
            a["href"] = BASE + h
        a["target"] = "_blank"
        a["rel"] = "noopener"
    for img in main.find_all("img"):
        img.attrs.pop("srcset", None)
        img["loading"] = "lazy"
    return main


def main():
    sheet = json.loads((DATA / "sheet.json").read_text(encoding="utf-8"))
    adir = DATA / "articles"
    have = {p.stem for p in adir.glob("*.json")}

    problems = [p for c in sheet["sections"] for s in c["subcategories"]
                for p in s["problems"]]
    missing = [p for p in problems
               if not (p.get("article_slug") and p["article_slug"] in have)]
    print(f"{len(missing)} problems still without an article")

    outline = load_outline()
    print(f"{len(outline)} problem nodes on the new sheet")

    by_norm = {}
    for n in outline:
        by_norm.setdefault(norm(n["label"]), n)
    keys = list(by_norm)

    pairs, unmatched = [], []
    for p in missing:
        k = norm(p["name"])
        n = by_norm.get(k)
        if n is None:
            close = difflib.get_close_matches(k, keys, n=1, cutoff=0.86)
            n = by_norm[close[0]] if close else None
        if n is None:
            unmatched.append(p["name"])
        else:
            pairs.append((p, n))

    print(f"matched {len(pairs)}, unmatched {len(unmatched)}")

    added, failed, thin = 0, [], []
    for i, (p, n) in enumerate(pairs, 1):
        path = n["href"].split("?")[0]
        url = BASE + path
        slug = slugify(url)
        dest = adir / f"{slug}.json"

        if not dest.exists():
            html = http_get(url, throttle=False)
            if not html:
                failed.append({"name": p["name"], "url": url})
                print(f"[{i}/{len(pairs)}] FAIL {p['name'][:45]}")
                continue
            main_el = clean_main(html)
            text = main_el.get_text(" ", strip=True) if main_el else ""
            if not main_el or len(text) < 250:
                thin.append({"name": p["name"], "url": url, "len": len(text)})
                print(f"[{i}/{len(pairs)}] thin({len(text)}) {p['name'][:40]}")
                continue
            body = "".join(str(c) for c in main_el.contents)
            dest.write_text(json.dumps({
                "slug": slug, "title": p["name"], "source_url": url,
                "extracted_by": "live-ssr", "length": len(body),
                "code_blocks": body.count("<pre"),
                "images": body.count("<img"), "html": body,
            }, ensure_ascii=False), encoding="utf-8")
            added += 1
            print(f"[{i}/{len(pairs)}] ok {len(text):6} chars  {p['name'][:42]}")

        p["article"] = url
        p["article_slug"] = slug

    (DATA / "sheet.json").write_text(
        json.dumps(sheet, indent=1, ensure_ascii=False), encoding="utf-8")
    (DATA / "restored_report.json").write_text(json.dumps(
        {"matched": len(pairs), "added": added, "failed": failed,
         "thin": thin, "unmatched": unmatched}, indent=1,
        ensure_ascii=False), encoding="utf-8")
    print(f"\nadded {added} articles, {len(thin)} thin, {len(failed)} failed, "
          f"{len(unmatched)} unmatched (see data/restored_report.json)")


if __name__ == "__main__":
    main()
