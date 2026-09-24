"""Upgrade problems to full editorials from takeuforward's public /blogs/ pages.

Pass 1 indexes every DSA blog post in the sitemap by its real <h1> title, which
is far more reliable than guessing slugs from problem names. Pass 2 matches the
problems that still lack a full article and writes them out.

The HTTP cache means pass 2 re-reads pass 1's downloads for free.
"""
import difflib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bs4 import BeautifulSoup

from blogs import fetch_blog
from common import DATA, SITE, http_get, slugify

SITEMAP = "https://takeuforward.org/sitemap.xml"
BLOG_MARK = "/blogs/data-structure-and-algorithm/"

STOP = {"a", "an", "the", "of", "in", "to", "and", "or", "for", "using",
        "with", "from", "is", "as", "by", "on", "its", "problem", "array"}


def toks(s: str):
    s = s.lower().replace("&", "and").replace("'", "")
    s = re.sub(r"\(.*?\)", "", s).split("|")[0]
    return [w for w in re.split(r"[^a-z0-9]+", s) if w and w not in STOP]


def norm(s: str) -> str:
    return " ".join(toks(s))


def blog_urls():
    xml = http_get(SITEMAP, throttle=False)
    if not xml:
        raise SystemExit("could not fetch the sitemap")
    return [u for u in re.findall(r"<loc>([^<]+)</loc>", xml) if BLOG_MARK in u]


def build_index(urls):
    """url -> title, cached on disk so this only really runs once."""
    cache = DATA / "blog_index.json"
    idx = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
    todo = [u for u in urls if u not in idx]
    print(f"indexing {len(todo)} blog posts ({len(idx)} already known)")
    for i, u in enumerate(todo, 1):
        html = http_get(u, throttle=False)
        if not html:
            idx[u] = None
        else:
            soup = BeautifulSoup(html, "lxml")
            h1 = soup.find("h1")
            idx[u] = h1.get_text(strip=True) if h1 else None
        if i % 40 == 0:
            print(f"  [{i}/{len(todo)}]")
            cache.write_text(json.dumps(idx, indent=1, ensure_ascii=False),
                             encoding="utf-8")
    cache.write_text(json.dumps(idx, indent=1, ensure_ascii=False),
                     encoding="utf-8")
    return {u: t for u, t in idx.items() if t}


def match(problems, index):
    """Match on title, then slug; require strong similarity AND token overlap
    so near-misses like 'Functions ...' -> 'z-function' are rejected."""
    entries = []
    for u, t in index.items():
        entries.append((u, norm(t), set(toks(t)),
                        norm(u.rsplit("/", 1)[-1].replace("-", " "))))
    by_title = {e[1]: e for e in entries}
    by_slug = {e[3]: e for e in entries}
    titles = list(by_title)
    slugs = list(by_slug)

    out, misses = [], []
    for p in problems:
        k, pt = norm(p["name"]), set(toks(p["name"]))
        e = by_title.get(k) or by_slug.get(k)
        how = "exact"
        if e is None:
            cand = (difflib.get_close_matches(k, titles, n=3, cutoff=0.74)
                    + difflib.get_close_matches(k, slugs, n=3, cutoff=0.74))
            best, score = None, 0.0
            for c in cand:
                ent = by_title.get(c) or by_slug.get(c)
                ov = len(pt & ent[2]) / max(1, len(pt))
                sim = difflib.SequenceMatcher(None, k, c).ratio()
                s = ov * 0.6 + sim * 0.4
                if ov >= 0.55 and sim >= 0.7 and s > score:
                    best, score = ent, s
            e, how = best, "fuzzy"
        if e is None:
            misses.append(p["name"])
        else:
            out.append((p, e[0], how))
    return out, misses


def main():
    sheet_built = SITE / "data" / "sheet.json"
    src = sheet_built if sheet_built.exists() else DATA / "sheet.json"
    sheet = json.loads(src.read_text(encoding="utf-8"))
    problems = [p for c in sheet["sections"] for s in c["subcategories"]
                for p in s["problems"]]
    need = [p for p in problems if p.get("article_kind") in (None, "statement")]
    print(f"{len(need)} problems lack a full article")

    index = build_index(blog_urls())
    print(f"{len(index)} blog posts indexed")

    pairs, misses = match(need, index)
    print(f"matched {len(pairs)}, unmatched {len(misses)}")

    adir = DATA / "articles"
    added, weak = 0, []
    byid = {p["id"]: p for p in problems}

    for i, (p, url, how) in enumerate(pairs, 1):
        slug = slugify(url)
        dest = adir / f"{slug}.json"
        if not dest.exists():
            rec = fetch_blog(url)
            if not rec or rec["text_len"] < 600:
                weak.append({"name": p["name"], "url": url,
                             "len": rec["text_len"] if rec else 0})
                print(f"[{i}/{len(pairs)}] weak {p['name'][:42]}")
                continue
            # Guard the fuzzy matches: the page's own title must resemble the
            # problem, otherwise we would file the wrong editorial.
            sim = difflib.SequenceMatcher(
                None, norm(p["name"]), norm(rec["title"])).ratio()
            if how == "fuzzy" and sim < 0.5:
                weak.append({"name": p["name"], "url": url,
                             "why": f"title mismatch ({rec['title']})"})
                print(f"[{i}/{len(pairs)}] REJECT {p['name'][:32]} != {rec['title'][:28]}")
                continue
            dest.write_text(json.dumps({
                "slug": slug, "title": rec["title"] or p["name"],
                "source_url": url, "extracted_by": "blog",
                "length": len(rec["html"]), "code_blocks": rec["code_blocks"],
                "images": rec["html"].count("<img"), "html": rec["html"],
            }, ensure_ascii=False), encoding="utf-8")
            added += 1
            print(f"[{i}/{len(pairs)}] ok {rec['text_len']:6}ch "
                  f"{rec['code_blocks']} code  {p['name'][:38]}")
        byid[p["id"]]["article"] = url
        byid[p["id"]]["article_slug"] = slug

    (DATA / "sheet.json").write_text(
        json.dumps(sheet, indent=1, ensure_ascii=False), encoding="utf-8")
    (DATA / "blog_report.json").write_text(json.dumps(
        {"matched": len(pairs), "added": added, "weak": weak,
         "unmatched": misses}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nadded {added} full editorials, {len(weak)} rejected/weak, "
          f"{len(misses)} unmatched (see data/blog_report.json)")


if __name__ == "__main__":
    main()
