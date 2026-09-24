"""Generate the static site from data/ into site/."""
import html as htmllib
import json
import re
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bs4 import BeautifulSoup, Comment
from common import DATA, SITE

LANG_LABEL = {"cpp": "C++", "c": "C", "java": "Java", "python": "Python",
              "py": "Python", "javascript": "JavaScript", "js": "JavaScript",
              "csharp": "C#", "go": "Go"}

INDEX_TMPL = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Striver's A2Z DSA Sheet - Offline Archive</title>
<link rel="stylesheet" href="style.css?v=%(ver)s">
</head><body>
<header><div class="wrap hd">
  <h1>Striver's A2Z DSA Sheet</h1>
  <span class="sub">offline archive &middot; %(narticles)d articles</span>
  <span class="spacer"></span>
  <button class="btn" id="expand">Expand / collapse all</button>
  <button class="btn" id="export">Export progress</button>
  <button class="btn" id="import">Import</button>
  <input type="file" id="file" accept="application/json" style="display:none">
</div></header>

<div class="wrap">
  <div class="stats">
    <div class="stat"><div class="k">Overall</div><div class="v" id="p-total">0 / 0</div></div>
    <div class="stat easy"><div class="k">Easy</div><div class="v" id="p-easy">0 / 0</div></div>
    <div class="stat medium"><div class="k">Medium</div><div class="v" id="p-medium">0 / 0</div></div>
    <div class="stat hard"><div class="k">Hard</div><div class="v" id="p-hard">0 / 0</div></div>
    <div class="stat" style="flex:1;min-width:210px">
      <div class="k">Progress <span id="p-pct" style="float:right">0.0%%</span></div>
      <div class="bar"><i id="p-bar"></i></div>
    </div>
  </div>

  <div class="controls">
    <input type="search" id="q" placeholder="Search problems...">
    <select id="f-diff">
      <option value="">All difficulties</option>
      <option>Easy</option><option>Medium</option><option>Hard</option>
    </select>
    <select id="f-status">
      <option value="">All problems</option>
      <option value="unsolved">Unsolved</option>
      <option value="solved">Solved</option>
      <option value="revision">Marked for revision</option>
    </select>
  </div>

  <div id="sections"></div>
  <footer>
    Personal offline archive of takeuforward.org content, rebuilt from the Wayback Machine.<br>
    Progress is stored in this browser only. Export it to keep a backup.
  </footer>
</div>
<script>window.__V="%(ver)s";</script>
<script src="app.js?v=%(ver)s"></script>
</body></html>
"""

ARTICLE_TMPL = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>%(title)s</title>
<link rel="stylesheet" href="../style.css?v=%(ver)s">
</head><body>
<header><div class="wrap hd">
  <a class="btn" href="../index.html">&larr; Back to sheet</a>
  <span class="spacer"></span>
  <span class="sub">archived copy</span>
</div></header>
<article class="article">
  <h1>%(title)s</h1>
  <div class="meta">Archived from <code>%(source)s</code></div>
  %(body)s
</article>
<script src="../article.js?v=%(ver)s"></script>
</body></html>
"""


def _tabify(soup, entries):
    """entries: list of (lang, <pre>). Builds one tabbed widget before the first pre."""
    if not entries:
        return
    first = entries[0][1]
    wrap = soup.new_tag("div"); wrap["class"] = "codewrap"
    tabs = soup.new_tag("div"); tabs["class"] = "tabs"
    first.insert_before(wrap)
    wrap.append(tabs)
    for i, (lang, pre) in enumerate(entries):
        label = LANG_LABEL.get(lang, (lang or "").upper() or f"Code {i + 1}")
        b = soup.new_tag("button")
        b["class"] = "tab on" if i == 0 else "tab"
        b["data-i"] = str(i)
        b.string = label
        tabs.append(b)
        pre.extract()
        pre["data-i"] = str(i)
        if i:
            pre["class"] = (pre.get("class") or []) + ["hidden"]
        wrap.append(pre)
    cp = soup.new_tag("button"); cp["class"] = "copy"; cp.string = "Copy"
    tabs.append(cp)


def _lang_of(block, pre):
    lang = (block.get("data-lang") or "").lower() if block is not None else ""
    if lang:
        return lang
    code = pre.find("code")
    if code is None:
        return ""
    lang = (code.get("lang") or "").lower()
    if lang:
        return lang
    for c in (code.get("class") or []):
        if c.startswith("language-"):
            return c[9:].lower()
    return ""


def group_code_blocks(soup):
    """Build one tabbed widget per language group.

    The archived markup nests each <pre> inside its own
    div.code-block[data-lang], all of them under a div.code-content - so the
    <pre> tags are cousins, not siblings, and must be grouped via the wrapper.
    """
    done = set()

    for holder in soup.find_all("div", class_="code-content"):
        entries = []
        for block in holder.find_all("div", class_="code-block"):
            pre = block.find("pre")
            if pre is None:
                continue
            entries.append((_lang_of(block, pre), pre))
            done.add(id(pre))
        _tabify(soup, entries)
        for block in holder.find_all("div", class_="code-block"):
            if not block.find("pre"):
                block.decompose()

    # Fallback for templates without .code-content: runs of sibling <pre>.
    pres = [p for p in soup.find_all("pre")
            if "wp-block-code" in (p.get("class") or []) and id(p) not in done]
    for pre in pres:
        if id(pre) in done:
            continue
        run, nxt = [pre], pre.find_next_sibling()
        while nxt is not None and nxt.name == "pre" and "wp-block-code" in (nxt.get("class") or []):
            run.append(nxt); nxt = nxt.find_next_sibling()
        for p in run:
            done.add(id(p))
        _tabify(soup, [(_lang_of(None, p), p) for p in run])


def clean_article(raw_html: str) -> str:
    soup = BeautifulSoup(raw_html, "lxml")
    for t in soup.find_all(["script", "style", "iframe", "noscript"]):
        t.decompose()
    # Authoring comments ("This is Examples Drop-Down") otherwise leak as text.
    for c in soup.find_all(string=lambda x: isinstance(x, Comment)):
        c.extract()
    # The archived markup carries a line-number gutter that no longer lines up.
    for d in soup.find_all("div", class_=re.compile("line-numbers", re.I)):
        d.decompose()
    for a in soup.find_all("a", href=True):
        if a["href"].startswith("http"):
            a["target"] = "_blank"; a["rel"] = "noopener"
    for img in soup.find_all("img"):
        img.attrs.pop("srcset", None)
        img["loading"] = "lazy"
    # The original collapses approach/code/complexity accordions. Offline the
    # point is reading, so open them all; they stay toggleable.
    for d in soup.find_all("details"):
        d["open"] = ""
    group_code_blocks(soup)
    body = soup.body or soup
    return "".join(str(c) for c in body.contents)


# Bumped every build so browsers never serve a stale app.js/sheet.json.
VER = str(int(time.time()))


def main():
    sheet = json.loads((DATA / "sheet.json").read_text(encoding="utf-8"))
    adir = DATA / "articles"
    have = {p.stem for p in adir.glob("*.json")} if adir.exists() else set()
    # Archived articles carry the full editorial; pages recovered from the
    # relaunched site are statement-only, since the solution tab needs a login.
    kind = {}
    for p in adir.glob("*.json"):
        try:
            kind[p.stem] = ("statement"
                            if json.loads(p.read_text(encoding="utf-8")).get(
                                "extracted_by") == "live-ssr" else "article")
        except Exception:
            kind[p.stem] = "article"

    (SITE / "articles").mkdir(parents=True, exist_ok=True)
    (SITE / "data").mkdir(parents=True, exist_ok=True)

    # Mark which problems actually have a usable archived article.
    missing = 0
    for cat in sheet["sections"]:
        for sub in cat["subcategories"]:
            for p in sub["problems"]:
                ok = bool(p.get("article_slug")) and p["article_slug"] in have
                p["article_available"] = ok
                p["article_kind"] = kind.get(p.get("article_slug")) if ok else None
                if not ok:
                    missing += 1
    (SITE / "data" / "sheet.json").write_text(
        json.dumps(sheet, ensure_ascii=False), encoding="utf-8")

    n = 0
    for f in sorted(adir.glob("*.json")):
        rec = json.loads(f.read_text(encoding="utf-8"))
        body = clean_article(rec["html"])
        out = ARTICLE_TMPL % {
            "title": htmllib.escape(rec["title"]),
            "source": htmllib.escape(rec["source_url"]),
            "body": body, "ver": VER,
        }
        (SITE / "articles" / f"{rec['slug']}.html").write_text(out, encoding="utf-8")
        n += 1

    (SITE / "index.html").write_text(
        INDEX_TMPL % {"narticles": n, "ver": VER}, encoding="utf-8")

    print(f"built {n} article pages")
    print(f"problems without a usable article: {missing}")
    print(f"site written to {SITE}")


if __name__ == "__main__":
    main()
