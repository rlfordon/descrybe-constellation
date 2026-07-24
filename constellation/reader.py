"""Case-reader server-side document prep (ux-spec.md Phase 3, items 8-10).

Two responsibilities:
  - sanitize_opinion_html: allowlist-based HTML sanitizer (stdlib html.parser
    only -- no third-party HTML library in this repo).
  - build_reader: resolve a cluster's opinion text, sanitize it, split into
    paragraphs, anchor each Descrybe issue passage into a paragraph via
    constellation.anchor, and inject highlight markup.

Anchoring is paragraph-level only (feasibility report Sec 5/6's offset-
mapping caveat): exact hits get a real <mark> span when the passage survives
as a literal, uninterrupted substring of the paragraph's sanitized HTML (safe
because a literal string match can't have crossed a tag boundary -- a tag
boundary always introduces a '<' character, which would break the match);
everything else (normalized/fuzzy hits, or exact hits whose span happens to
cross inline markup like a citation <em>) degrades to a paragraph-level
class + data-passage attribute, never a fragile char-offset splice.
"""

import html
import re
from html.parser import HTMLParser

from . import anchor

PRIMARY_FIELD = "html_with_citations"


class NoOpinionText(Exception):
    """Raised when no sub-opinion of a cluster has usable opinion text."""


# ------------------------------------------------------------------ sanitizer

_ALLOWED_TAGS = {"p", "span", "blockquote", "em", "i", "b", "strong",
                  "h1", "h2", "h3", "h4", "h5", "h6", "br"}
_DROP_TAGS = {"script", "style", "iframe", "img", "link"}
_ATTR_ALLOWED = {"p": {"id", "class"}, "span": {"id", "class"}}
_VOID_TAGS = {"br"}


class _Sanitizer(HTMLParser):
    """Allowlist sanitizer: unknown/disallowed tags (including <a>) are
    unwrapped -- the tag is dropped but its text/children still stream
    through -- except script/style/iframe/img/link, whose entire subtree is
    dropped (their "content" is code/markup, not opinion text). Only id and
    class survive on p/span; every other attribute (href included) is gone,
    so no external URL can survive in the output."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self._drop_depth = 0

    def handle_starttag(self, tag, attrs):
        self._start(tag, attrs)

    def handle_startendtag(self, tag, attrs):
        self._start(tag, attrs)
        self.handle_endtag(tag)

    def _start(self, tag, attrs):
        if self._drop_depth:
            if tag in _DROP_TAGS:
                self._drop_depth += 1
            return
        if tag in _DROP_TAGS:
            self._drop_depth += 1
            return
        if tag not in _ALLOWED_TAGS:
            return  # unwrap: strip the tag (a, div, table, sup, font, ...)
        allowed = _ATTR_ALLOWED.get(tag, set())
        kept = [(k, v) for k, v in attrs if k in allowed]
        attr_str = "".join(f' {k}="{html.escape(v or "", quote=True)}"' for k, v in kept)
        self.out.append(f"<{tag}{attr_str}>")

    def handle_endtag(self, tag):
        if self._drop_depth:
            if tag in _DROP_TAGS:
                self._drop_depth -= 1
            return
        if tag not in _ALLOWED_TAGS or tag in _VOID_TAGS:
            return
        self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if self._drop_depth:
            return
        self.out.append(html.escape(data))

    def get_html(self):
        return "".join(self.out)


def sanitize_opinion_html(raw):
    """Sanitize a raw CourtListener html_with_citations string down to the
    allowlisted tag set. Returns "" for falsy input."""
    if not raw:
        return ""
    p = _Sanitizer()
    p.feed(raw)
    p.close()
    return p.get_html()


# ------------------------------------------------------------- paragraph split

_PARA_RE = re.compile(r"<(p|blockquote)\b([^>]*)>(.*?)</\1>", re.S | re.I)
_ID_ATTR_RE = re.compile(r'\bid="([^"]*)"')
_CLASS_ATTR_RE = re.compile(r'\sclass="([^"]*)"')
_TAG_RE = re.compile(r"<[^>]+>")


def _to_text(markup):
    """Tag-stripped, HTML-entity-unescaped, whitespace-collapsed plain text
    for a paragraph's inner HTML -- the same 'tags to a space, then unescape'
    approach as scripts/measure_anchoring.py's html_to_text, plus whitespace
    collapse since this feeds anchor.anchor_passage's paragraph_text, not a
    full-opinion measurement corpus."""
    text = html.unescape(_TAG_RE.sub(" ", markup or ""))
    return re.sub(r"\s+", " ", text).strip()


def _split_segments(sanitized_html):
    """Split already-sanitized HTML into paragraph-unit segments (<p> and
    <blockquote> blocks, which is what carries CourtListener's <p id="...">
    anchors -- report Sec 7) and pass-through "other" segments for everything
    between them (headers, stray <br>). Regex-based rather than a second
    parser pass: sanitize_opinion_html already produced a small, well-formed
    tag vocabulary, so this is a controlled re-split of our own output, not a
    second security boundary."""
    segments = []
    pos = 0
    n = 0
    for m in _PARA_RE.finditer(sanitized_html):
        if m.start() > pos:
            other = sanitized_html[pos:m.start()]
            if other.strip():
                segments.append({"type": "other", "raw": other})
        tag, attrs, inner = m.group(1), m.group(2), m.group(3)
        n += 1
        id_m = _ID_ATTR_RE.search(attrs)
        pid = id_m.group(1) if id_m else f"p-{n}"
        segments.append({
            "type": "para", "id": pid, "tag": tag, "attrs": attrs, "inner": inner,
        })
        pos = m.end()
    if pos < len(sanitized_html):
        tail = sanitized_html[pos:]
        if tail.strip():
            segments.append({"type": "other", "raw": tail})
    if not any(s["type"] == "para" for s in segments) and sanitized_html.strip():
        # No <p>/<blockquote> at all (not seen in the measured corpus, but
        # html.parser output should never crash the reader on it) -- treat
        # the whole document as one synthesized paragraph.
        segments = [{"type": "para", "id": "p-1", "tag": "p", "attrs": "",
                     "inner": sanitized_html}]
    return segments


def _merge_class(attrs, add_class):
    m = _CLASS_ATTR_RE.search(attrs)
    if m:
        merged = (m.group(1) + " " + add_class).strip()
        return _CLASS_ATTR_RE.sub(f' class="{merged}"', attrs, count=1)
    return attrs + f' class="{add_class}"'


def _render_paragraph(seg, exact_hits, para_hit_indices):
    """seg: a 'para' segment. exact_hits: [(passage_index, passage_text), ...]
    anchored "exact" to this paragraph. para_hit_indices: passage indices
    (any status) that should get the paragraph-level treatment for this
    paragraph -- either because their status wasn't exact, or because an
    exact match's text didn't survive as a literal substring of the sanitized
    inner HTML (inline markup, e.g. a citation <em>, interrupted it)."""
    inner = seg["inner"]
    injected = set()
    for idx, text in exact_hits:
        if text and text in inner:
            inner = inner.replace(
                text, f'<mark class="passage-hit" data-passage="{idx}">{text}</mark>', 1
            )
            injected.add(idx)

    degraded = sorted(para_hit_indices | {idx for idx, _ in exact_hits if idx not in injected})
    attrs = seg["attrs"]
    if degraded:
        attrs = _merge_class(attrs, "passage-para")
        attrs = attrs + f' data-passage="{" ".join(str(i) for i in degraded)}"'
    return f'<{seg["tag"]}{attrs}>{inner}</{seg["tag"]}>'


# ------------------------------------------------------------------- reader

def _resolve_opinion_html(cluster_id, cl):
    """First sub-opinion (in cl.opinion_ids order) with non-empty
    html_with_citations. Returns (opinion_id, html)."""
    opinion_ids = cl.opinion_ids(cluster_id)
    for oid in opinion_ids:
        raw = cl.opinion_html(oid)
        if raw:
            return oid, raw
    raise NoOpinionText(
        f"no sub-opinion of cluster {cluster_id} has {PRIMARY_FIELD} text "
        f"(checked {len(opinion_ids)} opinion(s))"
    )


def build_reader(case_id, focus, cl, dscb):
    """Resolve + sanitize the opinion, anchor Descrybe's focus-issue passages
    into it, and return {html, passages, unanchored, meta}.

    html: sanitized opinion HTML with exact hits wrapped in <mark
      class="passage-hit" data-passage="N"> and normalized/fuzzy-anchored
      paragraphs carrying class="passage-para" data-passage="N ...".
    passages: [{n, text, status, paragraph_id, ratio}, ...] in passage order.
    unanchored: the subset with status "unanchorable" (never dropped).
    meta: {case_id, focus, cluster_id, opinion_id, field, paragraph_count}.
    """
    from . import bridge
    from . import web  # lazy import: web imports this module (dossier.py's pattern)

    cluster_id = bridge.to_cluster_id(case_id)
    opinion_id, raw_html = _resolve_opinion_html(cluster_id, cl)
    sanitized = sanitize_opinion_html(raw_html)
    segments = _split_segments(sanitized)
    paragraphs = [(s["id"], _to_text(s["inner"])) for s in segments if s["type"] == "para"]

    raw_passages = web.case_passages(dscb, case_id, focus)
    passage_texts = anchor.parse_passages(raw_passages)

    passage_results = []
    exact_by_pid = {}
    para_by_pid = {}
    for i, text in enumerate(passage_texts, 1):
        result = anchor.anchor_passage(text, paragraphs)
        passage_results.append({
            "n": i, "text": text, "status": result["status"],
            "paragraph_id": result["paragraph_id"], "ratio": result["ratio"],
        })
        pid = result["paragraph_id"]
        if pid is None:
            continue
        if result["status"] == "exact":
            exact_by_pid.setdefault(pid, []).append((i, text))
        else:  # normalized / fuzzy -- paragraph-level only
            para_by_pid.setdefault(pid, set()).add(i)

    rendered = []
    for seg in segments:
        if seg["type"] != "para":
            rendered.append(seg["raw"])
            continue
        rendered.append(_render_paragraph(
            seg, exact_by_pid.get(seg["id"], []), para_by_pid.get(seg["id"], set())
        ))

    unanchored = [p for p in passage_results if p["status"] == "unanchorable"]

    return {
        "html": "".join(rendered),
        "passages": passage_results,
        "unanchored": unanchored,
        "meta": {
            "case_id": case_id, "focus": focus, "cluster_id": cluster_id,
            "opinion_id": opinion_id, "field": PRIMARY_FIELD,
            "paragraph_count": len(paragraphs),
        },
    }
