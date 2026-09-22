"""Fetch the archived A2Z sheet page and extract the full problem tree."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, clean, flight_payload, slugify, wayback_get

SHEET_URL = "https://takeuforward.org/dsa/strivers-a2z-sheet-learn-dsa-a-to-z"
SNAPSHOT = "20260423090911"

# Counts shown in the archived page header - used as an integrity guard.
EXPECTED = {"problems": 451, "categories": 18, "subcategories": 61,
            "Easy": 132, "Medium": 183, "Hard": 136}


def extract_array(payload: str, anchor: str):
    """Bracket-match a JSON array that begins at `anchor` and json.loads it."""
    start = payload.find(anchor)
    if start == -1:
        raise SystemExit(f"anchor {anchor!r} not found in flight payload")
    i = start + len(anchor) - 1          # position of the opening '['
    depth, j, in_str, esc = 0, i, False, False
    while j < len(payload):
        c = payload[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c in "[{":
                depth += 1
            elif c in "]}":
                depth -= 1
                if depth == 0:
                    return json.loads(payload[i:j + 1])
        j += 1
    raise SystemExit("unterminated array in flight payload")


def main():
    print(f"fetching sheet index from archive ({SNAPSHOT}) ...")
    html = wayback_get(SHEET_URL, SNAPSHOT)
    if not html:
        raise SystemExit("could not fetch the sheet page from the archive")

    payload = flight_payload(html)
    print(f"  flight payload: {len(payload):,} chars")
    sections = extract_array(payload, '"sections":[')

    out, seen_articles = [], {}
    tally = {"Easy": 0, "Medium": 0, "Hard": 0}
    n_problems = n_subs = 0

    for cat in sections:
        c = {"id": cat.get("category_id"),
             "name": cat.get("category_name"),
             "subcategories": []}
        for sub in cat.get("subcategories") or []:
            n_subs += 1
            s = {"id": sub.get("subcategory_id"),
                 "name": sub.get("subcategory_name"),
                 "problems": []}
            for p in sub.get("problems") or []:
                n_problems += 1
                article = clean(p.get("article"))
                slug = slugify(article) if article else None
                if article:
                    seen_articles[article] = slug
                # A couple of records use lowercase ("medium"/"hard"); normalise.
                diff = (clean(p.get("difficulty")) or "Easy").strip().capitalize()
                tally[diff] = tally.get(diff, 0) + 1
                s["problems"].append({
                    "id": p.get("problem_id"),
                    "name": (clean(p.get("problem_name")) or "").strip(),
                    "difficulty": diff,
                    "article": article,
                    "article_slug": slug,
                    "youtube": clean(p.get("youtube")),
                    "leetcode": clean(p.get("leetcode")),
                    "practice": clean(p.get("link")),
                })
            c["subcategories"].append(s)
        out.append(c)

    got = {"problems": n_problems, "categories": len(out),
           "subcategories": n_subs, **tally}
    print("\n  parsed:", json.dumps(got))
    print("  expect:", json.dumps(EXPECTED))

    bad = {k: (got.get(k), v) for k, v in EXPECTED.items() if got.get(k) != v}
    if bad:
        # Fail loudly: a silent shortfall here corrupts the whole archive.
        raise SystemExit(f"\nINTEGRITY CHECK FAILED (got, expected): {bad}")
    print("  integrity check passed")

    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "sheet.json").write_text(
        json.dumps({"source": SHEET_URL, "snapshot": SNAPSHOT,
                    "totals": got, "sections": out},
                   indent=1, ensure_ascii=False), encoding="utf-8")

    articles = [{"url": u, "slug": s} for u, s in sorted(seen_articles.items())]
    (DATA / "articles.json").write_text(
        json.dumps(articles, indent=1, ensure_ascii=False), encoding="utf-8")

    no_article = sum(1 for c in out for s in c["subcategories"]
                     for p in s["problems"] if not p["article"])
    print(f"\n  wrote data/sheet.json     ({n_problems} problems)")
    print(f"  wrote data/articles.json ({len(articles)} unique articles)")
    print(f"  problems without an article: {no_article}")


if __name__ == "__main__":
    main()
