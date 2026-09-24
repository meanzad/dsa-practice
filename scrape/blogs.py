"""Extract a full solution article from takeuforward's /blogs/... pages.

These carry the real editorials: problem statement, approaches, dry run, and
working code in C++/Python/Java/JavaScript, and they are public.

The prose is server-rendered into <article class="...editorialContent">, but the
code is only rendered there as a Monaco preview with line numbers welded into the
text. The clean source sits in the RSC flight payload under `code_editor`, so the
two are merged: DOM for prose, payload for code. Payload blocks are not in
document order, so they are matched to their DOM slot by content.
"""
import re

from bs4 import BeautifulSoup, Comment

from common import flight_payload, http_get
from fetch_index import extract_array

BASE = "https://takeuforward.org"
BLOG_PREFIX = BASE + "/blogs/data-structure-and-algorithm/"

LANG_LABEL = {"cpp": "C++", "c": "C", "java": "Java", "python": "Python",
              "javascript": "JavaScript", "js": "JavaScript", "csharp": "C#"}

NOISE = re.compile(
    r"advertisement|log ?in ?/ ?sign ?up|log in or sign up|see plans and pricing"
    r"|early bird offer|sale ends?|subscribe|upgrade to|takeuforward plus", re.I)


def _resolve_row(payload: str, ref: str):
    """Resolve an RSC "$<ref>" pointer to its "<ref>:T<hexlen>," text row.

    Unlike the article pages, blog payloads do not start these rows on a fresh
    line, so the header cannot be anchored to one - only guarded against
    matching the tail of a longer hex id. The length prefix is a byte count.
    """
    m = re.search(r"(?<![0-9a-f])" + re.escape(ref) + r":T([0-9a-f]+),", payload)
    if not m:
        return None
    nbytes = int(m.group(1), 16)
    return payload[m.end():].encode("utf-8")[:nbytes].decode("utf-8", "ignore")


def _sig(code: str) -> str:
    """Comparable signature: letters/digits only, so line numbers and
    whitespace differences between the DOM preview and the payload drop out."""
    return re.sub(r"[^a-z0-9]+", "", (code or "").lower())[:400]


TAB_WORDS = {"c++", "python", "java", "javascript", "c#", "c", "go"}


def _strip_tab_labels(text: str) -> str:
    """The preview's text starts with its own tab labels; drop that run."""
    lines = text.split("\n")
    i = 0
    while i < len(lines) and lines[i].strip().lower() in TAB_WORDS:
        i += 1
    return "\n".join(lines[i:])


def _guess_lang(code: str) -> str:
    if "#include" in code or "std::" in code or "using namespace" in code:
        return "cpp"
    if re.search(r"\bpublic\s+class\b|System\.out\.", code):
        return "java"
    if re.search(r"^\s*def\s|\bprint\(", code, re.M) and "{" not in code[:200]:
        return "python"
    if re.search(r"\bfunction\b|console\.log|=>", code):
        return "javascript"
    return "cpp"


def _overlap(a: str, b: str) -> int:
    """Length of the longest shared prefix-ish run: how much of `a` appears
    contiguously in `b`. Cheap and good enough to pair a preview with source."""
    for n in (400, 300, 200, 120, 80, 60):
        if len(a) >= n and a[:n] in b:
            return n
    return 0


def fetch_blog(url: str):
    html = http_get(url, throttle=False)
    if not html:
        return None
    soup = BeautifulSoup(html, "lxml")
    art = soup.find("article", class_=re.compile("editorialContent"))
    if art is None:
        return None

    payload = flight_payload(html)
    blocks = []
    try:
        for s in extract_array(payload, '"sections":['):
            blocks.extend(s.get("code_editor") or [])
    except SystemExit:
        blocks = []

    # tab_content is inline on some posts and an RSC reference ("$60") on
    # others; resolve the references so every post yields real source.
    for b in blocks:
        for d in b.get("data") or []:
            v = d.get("tab_content")
            if isinstance(v, str) and re.fullmatch(r"\$[0-9a-f]+", v or ""):
                d["tab_content"] = _resolve_row(payload, v[1:]) or ""

    # Signature of every language variant, so a DOM slot can be identified
    # whichever language it happens to be showing. Kept as a list, not a dict:
    # two approaches in one post often share an opening, and keying on that
    # prefix would silently drop one of them.
    sigs = [(b, [_sig(d.get("tab_content")) for d in (b.get("data") or [])
                 if len(_sig(d.get("tab_content"))) > 40]) for b in blocks]

    for t in art.find_all(["script", "style", "noscript", "iframe", "svg",
                           "input", "textarea", "form"]):
        t.decompose()
    for c in art.find_all(string=lambda x: isinstance(x, Comment)):
        c.extract()

    # Strip the page's own buttons BEFORE building widgets - otherwise this
    # would delete the tab and copy buttons that were just inserted.
    for b in art.find_all("button"):
        b.decompose()

    slots = art.find_all("div", class_=re.compile("codeSection"))
    used, replaced, fallbacks = set(), 0, 0
    for pos, sec in enumerate(slots):
        raw = sec.get_text("\n", strip=True)
        # The preview interleaves line numbers; drop standalone-number lines.
        code_txt = "\n".join(l for l in raw.split("\n") if not l.strip().isdigit())
        sig = _sig(code_txt)

        match, best = None, 0
        for b, variants in sigs:
            if id(b) in used:
                continue
            for v in variants:
                n = _overlap(v, sig)
                if n > best:
                    match, best = b, n
        if best < 60:
            match = None
        # When every slot has a block, position is a safe last resort - the
        # lists describe the same post in the same order.
        if match is None and len(slots) == len(sigs) and pos < len(sigs):
            cand = sigs[pos][0]
            if id(cand) not in used:
                match = cand
        widget = None
        if match is not None:
            used.add(id(match))
            widget = _code_widget(soup, match)
        # Many posts ship only the server-rendered language in the HTML and load
        # the other tabs on demand. Rather than emit empty <code> blocks, fall
        # back to the one language the preview actually contains.
        if widget is None or not widget.find("code", string=True):
            dom_code = _strip_tab_labels(code_txt).strip()
            if len(dom_code) < 40:
                continue
            widget = _dom_widget(soup, dom_code)
            fallbacks += 1
        sec.replace_with(widget)
        replaced += 1

    for el in art.find_all(["div", "section", "aside", "p", "span"]):
        txt = el.get_text(" ", strip=True)
        if txt and len(txt) < 120 and NOISE.search(txt):
            el.decompose()
    for a in art.find_all("a", href=True):
        if a["href"].startswith("/"):
            a["href"] = BASE + a["href"]
        a["target"] = "_blank"
        a["rel"] = "noopener"
    for img in art.find_all("img"):
        img.attrs.pop("srcset", None)
        img["loading"] = "lazy"

    body = "".join(str(c) for c in art.contents)
    title = soup.find("h1")
    return {
        "html": body,
        "title": (title.get_text(strip=True) if title else "").strip(),
        "code_blocks": replaced,
        "dom_fallbacks": fallbacks,
        "payload_blocks": len(blocks),
        "text_len": len(re.sub(r"\s+", " ", art.get_text(" ", strip=True))),
    }


def _code_widget(soup, block):
    """Build the same tabbed widget the archived articles use."""
    wrap = soup.new_tag("div"); wrap["class"] = "codewrap"
    tabs = soup.new_tag("div"); tabs["class"] = "tabs"
    wrap.append(tabs)
    entries = [d for d in (block.get("data") or [])
               if (d.get("tab_content") or "").strip()]
    for i, d in enumerate(entries):
        lang = (d.get("tab_title") or "").lower()
        b = soup.new_tag("button")
        b["class"] = "tab on" if i == 0 else "tab"
        b["data-i"] = str(i)
        b.string = LANG_LABEL.get(lang, lang.upper() or f"Code {i + 1}")
        tabs.append(b)

        pre = soup.new_tag("pre")
        pre["class"] = ["wp-block-code"] + ([] if i == 0 else ["hidden"])
        pre["data-i"] = str(i)
        code = soup.new_tag("code")
        code["lang"] = lang
        code["class"] = f"language-{lang}"
        code.string = d.get("tab_content") or ""
        pre.append(code)
        wrap.append(pre)
    if not entries:
        return wrap
    cp = soup.new_tag("button"); cp["class"] = "copy"; cp.string = "Copy"
    tabs.append(cp)
    return wrap


def _dom_widget(soup, code: str):
    """Single-language widget built from the rendered preview."""
    lang = _guess_lang(code)
    wrap = soup.new_tag("div"); wrap["class"] = "codewrap"
    tabs = soup.new_tag("div"); tabs["class"] = "tabs"
    b = soup.new_tag("button"); b["class"] = "tab on"; b["data-i"] = "0"
    b.string = LANG_LABEL.get(lang, lang.upper())
    tabs.append(b)
    cp = soup.new_tag("button"); cp["class"] = "copy"; cp.string = "Copy"
    tabs.append(cp)
    wrap.append(tabs)
    pre = soup.new_tag("pre"); pre["class"] = ["wp-block-code"]; pre["data-i"] = "0"
    code_el = soup.new_tag("code")
    code_el["lang"] = lang; code_el["class"] = f"language-{lang}"
    code_el.string = code
    pre.append(code_el); wrap.append(pre)
    return wrap
