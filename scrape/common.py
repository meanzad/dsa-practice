"""Shared helpers: Wayback fetching, throttling, caching, RSC flight-payload parsing."""
import hashlib
import json
import os
import re
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache"
DATA = ROOT / "data"
SITE = ROOT / "site"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " \
     "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"

DELAY = 1.0           # seconds between requests (Wayback rate-limits hard)
MAX_RETRIES = 5
_last_request = [0.0]

# One keep-alive session: opening a fresh TLS connection per request makes the
# archive drop us with ConnectionError far more often than it rate-limits us.
SESSION = requests.Session()
SESSION.headers["User-Agent"] = UA
SESSION.headers["Connection"] = "keep-alive"
_adapter = HTTPAdapter(pool_connections=4, pool_maxsize=8, max_retries=2)
SESSION.mount("https://", _adapter)
SESSION.mount("http://", _adapter)


def _throttle():
    gap = time.time() - _last_request[0]
    if gap < DELAY:
        time.sleep(DELAY - gap)
    _last_request[0] = time.time()


def _cache_path(key: str) -> Path:
    h = hashlib.sha256(key.encode()).hexdigest()[:24]
    return CACHE / f"{h}.bin"


def http_get(url: str, *, cache=True, binary=False, timeout=60, throttle=True):
    """GET with on-disk cache, throttle, and backoff on 429/503. Returns bytes/str or None."""
    cp = _cache_path(url)
    if cache and cp.exists():
        raw = cp.read_bytes()
        return raw if binary else raw.decode("utf-8", "replace")
    # Negative cache: Wayback 404s are deterministic, so never re-fetch them.
    miss = cp.with_suffix(".miss")
    if cache and miss.exists():
        return None

    delay = DELAY
    for attempt in range(MAX_RETRIES):
        if throttle:
            _throttle()
        try:
            r = SESSION.get(url, timeout=timeout)
        except Exception as e:
            print(f"    ! {type(e).__name__} {str(e)[:60]}")
            time.sleep(delay); delay = min(delay * 1.6, 20)
            continue

        if r.status_code == 200:
            CACHE.mkdir(parents=True, exist_ok=True)
            if cache:
                cp.write_bytes(r.content)
            return r.content if binary else r.text
        if r.status_code in (429, 503, 502, 504):
            print(f"    . {r.status_code}, backing off {delay:.0f}s")
            time.sleep(delay); delay *= 2
            continue
        if cache:                      # 404 and friends: genuine, record it
            CACHE.mkdir(parents=True, exist_ok=True)
            cp.with_suffix(".miss").write_text(str(r.status_code))
        return None
    return None


def wayback_url(url: str, timestamp: str = "2026") -> str:
    """`id_` suffix asks the archive for the raw original bytes, no injected toolbar."""
    return f"https://web.archive.org/web/{timestamp}id_/{url}"


def wayback_get(url: str, timestamp: str = "2026"):
    return http_get(wayback_url(url, timestamp))


# --- RSC flight payload -----------------------------------------------------

_PUSH_RE = re.compile(r'self\.__next_f\.push\(\s*\[\s*1\s*,\s*"', re.S)


def _read_js_string(s: str, i: int):
    """Read a JS double-quoted string starting at index i (just past the opening quote)."""
    out = []
    while i < len(s):
        c = s[i]
        if c == "\\":
            nxt = s[i + 1] if i + 1 < len(s) else ""
            if nxt == "u":
                try:
                    out.append(chr(int(s[i + 2:i + 6], 16))); i += 6; continue
                except ValueError:
                    out.append(nxt); i += 2; continue
            mapping = {"n": "\n", "t": "\t", "r": "\r", '"': '"',
                       "\\": "\\", "/": "/", "b": "\b", "f": "\f"}
            out.append(mapping.get(nxt, nxt)); i += 2; continue
        if c == '"':
            return "".join(out), i + 1
        out.append(c); i += 1
    return "".join(out), i


def flight_payload(html: str) -> str:
    """Concatenate every self.__next_f.push([1,"..."]) chunk, unescaped."""
    parts = []
    for m in _PUSH_RE.finditer(html):
        chunk, _ = _read_js_string(html, m.end())
        parts.append(chunk)
    return "".join(parts)


def iter_json_objects(payload: str, anchor: str):
    """Yield JSON objects that start at `anchor`, using brace matching.

    A non-greedy regex silently loses records when a field contains braces,
    so scan properly instead.
    """
    idx = 0
    while True:
        start = payload.find(anchor, idx)
        if start == -1:
            return
        depth, i, in_str, esc = 0, start, False, False
        while i < len(payload):
            c = payload[i]
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
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        blob = payload[start:i + 1]
                        try:
                            yield json.loads(blob)
                        except json.JSONDecodeError:
                            pass
                        break
            i += 1
        idx = start + 1


UNDEF = "$undefined"


def clean(v):
    """Normalise the RSC `$undefined` sentinel to None."""
    if v is None or v == UNDEF or (isinstance(v, str) and not v.strip()):
        return None
    return v


def slugify(url: str) -> str:
    path = re.sub(r"^https?://[^/]+/", "", url.rstrip("/"))
    s = re.sub(r"[^a-zA-Z0-9]+", "-", path).strip("-").lower()
    return s[:120] or "article"


ARCHIVE_PREFIX_RE = re.compile(
    r"https?://web\.archive\.org/web/\d+[a-z_]*/", re.I)


def strip_archive_urls(html: str) -> str:
    return ARCHIVE_PREFIX_RE.sub("", html)
