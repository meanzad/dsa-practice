"""Fetch every archived article and extract its body HTML from the RSC payload."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, flight_payload, strip_archive_urls, wayback_get

CONTENT_REF_RE = re.compile(r'"content":"\$([0-9a-f]+)"')
TITLE_RE = re.compile(r'"title","0",\{"children":"(.*?)"\}')
MIN_BODY = 400          # anything shorter is almost certainly a failed extraction


def resolve_chunk(payload: str, ref: str):
    """Resolve an RSC `$<ref>` pointer to its `<ref>:T<hexlen>,` text row.

    The declared length is a UTF-8 BYTE count, so slice on bytes - slicing on
    characters overshoots and drags the next row's header into the body.
    """
    m = re.search(r"(?:^|\n)" + re.escape(ref) + r":T([0-9a-f]+),", payload)
    if not m:
        return None
    nbytes = int(m.group(1), 16)
    return payload[m.end():].encode("utf-8")[:nbytes].decode("utf-8", "ignore")


def extract_body(payload: str):
    m = CONTENT_REF_RE.search(payload)
    if m:
        body = resolve_chunk(payload, m.group(1))
        if body:
            return body, "rsc-ref"
    # Fallback: some templates may inline the HTML directly.
    m = re.search(r'"content":"(<[^"]{400,})"', payload)
    if m:
        return m.group(1), "inline"
    return None, "not-found"


SCRIPT_RE = re.compile(r"<script\b.*?</script>", re.S | re.I)
LINKCSS_RE = re.compile(r'<link\b[^>]*rel="stylesheet"[^>]*>', re.I)


def sanitize(html: str) -> str:
    html = SCRIPT_RE.sub("", html)          # highlight.js loaders etc.
    html = LINKCSS_RE.sub("", html)
    html = strip_archive_urls(html)
    return html.strip()


def main():
    articles = json.loads((DATA / "articles.json").read_text(encoding="utf-8"))
    outdir = DATA / "articles"
    outdir.mkdir(parents=True, exist_ok=True)

    report = {"ok": [], "thin": [], "failed": []}
    total = len(articles)

    for n, a in enumerate(articles, 1):
        url, slug = a["url"], a["slug"]
        dest = outdir / f"{slug}.json"
        if dest.exists():
            report["ok"].append(slug)
            continue

        print(f"[{n}/{total}] {slug[:70]}")
        html = wayback_get(url)
        if not html:
            print("    FAILED: no snapshot")
            report["failed"].append({"slug": slug, "url": url, "why": "no-snapshot"})
            continue

        payload = flight_payload(html)
        body, how = extract_body(payload)
        if not body:
            print(f"    FAILED: {how}")
            report["failed"].append({"slug": slug, "url": url, "why": how})
            continue

        body = sanitize(body)
        tm = TITLE_RE.search(payload)
        title = (tm.group(1) if tm else slug).replace(" - Tutorial", "").strip()

        rec = {"slug": slug, "title": title, "source_url": url,
               "extracted_by": how, "length": len(body),
               "code_blocks": body.count("wp-block-code"),
               "images": body.count("<img"), "html": body}
        dest.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")

        if len(body) < MIN_BODY:
            print(f"    thin ({len(body)} chars)")
            report["thin"].append({"slug": slug, "url": url, "length": len(body)})
        else:
            report["ok"].append(slug)
            print(f"    ok  {len(body):,} chars, {rec['code_blocks']} code, {rec['images']} img")

    (DATA / "report.json").write_text(
        json.dumps({"total": total, "ok": len(report["ok"]),
                    "thin": report["thin"], "failed": report["failed"]},
                   indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\ndone: {len(report['ok'])} ok, {len(report['thin'])} thin, "
          f"{len(report['failed'])} failed  (see data/report.json)")


if __name__ == "__main__":
    main()
