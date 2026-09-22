"""Download article images locally and rewrite the HTML to point at them.

Images live on static.takeuforward.org, a public CDN that is unaffected by the
article pages 404-ing, so try it first and fall back to the Wayback copy.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, SITE, http_get, wayback_url

IMGDIR = SITE / "assets" / "img"
# Some archived tags write `src = "..."` with spaces around the equals sign, and
# the lookbehind keeps `data-src`/`lazy-src` from being mistaken for `src`.
SRC_RE = re.compile(r'<img\b[^>]*?(?<![-\w])src\s*=\s*"([^"]+)"', re.I)

EXTS = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif",
        "image/webp": ".webp", "image/svg+xml": ".svg"}


def local_name(url: str) -> str:
    h = hashlib.sha256(url.encode()).hexdigest()[:16]
    m = re.search(r"\.(png|jpe?g|gif|webp|svg)", url, re.I)
    ext = ("." + m.group(1).lower().replace("jpeg", "jpg")) if m else ".png"
    return h + ext


def main():
    IMGDIR.mkdir(parents=True, exist_ok=True)
    files = sorted((DATA / "articles").glob("*.json"))

    urls = set()
    for f in files:
        rec = json.loads(f.read_text(encoding="utf-8"))
        for u in SRC_RE.findall(rec["html"]):
            if u.startswith("http"):
                urls.add(u)

    print(f"{len(urls)} unique images referenced by {len(files)} articles")
    mapping, failed = {}, []

    for i, u in enumerate(sorted(urls), 1):
        name = local_name(u)
        dest = IMGDIR / name
        if dest.exists():
            mapping[u] = name
            continue
        data = http_get(u, binary=True, throttle=False)   # live CDN, not rate-limited
        if not data:
            data = http_get(wayback_url(u), binary=True)   # then the archive
        if not data:
            failed.append(u)
            print(f"[{i}/{len(urls)}] MISS {u[-60:]}")
            continue
        dest.write_bytes(data)
        mapping[u] = name
        if i % 25 == 0:
            print(f"[{i}/{len(urls)}] {len(mapping)} saved")

    # Rewrite article HTML to the local copies.
    rewritten = 0
    for f in files:
        rec = json.loads(f.read_text(encoding="utf-8"))
        html = rec["html"]
        new = SRC_RE.sub(
            lambda m: m.group(0).replace(
                m.group(1), "../assets/img/" + mapping[m.group(1)])
            if m.group(1) in mapping else m.group(0), html)
        if new != html:
            rec["html"] = new
            f.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
            rewritten += 1

    size = sum(p.stat().st_size for p in IMGDIR.glob("*")) / 1e6
    (DATA / "images.json").write_text(
        json.dumps({"saved": len(mapping), "failed": failed,
                    "size_mb": round(size, 1)}, indent=1), encoding="utf-8")
    print(f"\nsaved {len(mapping)} images ({size:.1f} MB), "
          f"{len(failed)} failed, rewrote {rewritten} articles")


if __name__ == "__main__":
    main()
