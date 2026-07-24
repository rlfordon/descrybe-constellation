"""Issue dossier: an issue-level document assembled from case-level Descrybe/
CourtListener parts. No LLM generation -- only retrieved text composed with
per-block source labels (design.md Amendments; there is no issue-level object
on Descrybe's MCP surface, only per-case summaries and per-case passages).
"""

import re
from datetime import datetime
from html import escape

from . import corpus as C

REVIEW_NOTE = "research support, not legal advice"


def _esc(text):
    """html.escape then neutralize '</' so no retrieved text can close an
    embedding tag early -- same defense as web.py's snapshot export."""
    return escape(str(text)).replace("</", "<\\/")


def _paragraphs(text):
    """Render a long prose block (summaries run ~23k chars) as <p> tags split
    on blank lines, each escaped; preserves in-paragraph line wraps."""
    if not text:
        return "<p><em>(empty)</em></p>"
    blocks = re.split(r"\n\s*\n", text.strip())
    return "\n".join(
        f'<p>{_esc(b).replace(chr(10), "<br>")}</p>' for b in blocks if b.strip()
    )


def _needs_verification(label):
    return f'<p class="nv">[Needs verification] &mdash; could not retrieve {escape(label)}</p>'


def _case_block(node, dscb, seed):
    """One <section> per leading case: name/court/date/numbers, then the
    three Descrybe blocks, each independently wrapped so one failure doesn't
    take down the others or the document."""
    case_id = node["case_id"]
    anchor = f"case-{node['cluster_id']}"
    name = _esc(node["name"])
    court = _esc(node.get("court") or "court unknown")
    date = _esc(node.get("date") or "date unknown")
    court_level = _esc(node.get("court_level") or "unknown")
    citation_count = node.get("citation_count")
    cited_by = node.get("cited_by_corpus", 0)

    header = [
        f'<h3 id="{anchor}">{name}</h3>',
        f'<p class="case-meta">{court} &mdash; {date} &mdash; court level: {court_level} '
        f'&mdash; citation count: {escape(str(citation_count if citation_count is not None else "?"))} '
        f'&mdash; cited by {cited_by} corpus member(s) <span class="tag">[CourtListener]</span></p>',
    ]
    if node.get("research_value") or node.get("treatment"):
        rv = _esc(node.get("research_value") or "")
        tr = _esc(node.get("treatment") or "")
        header.append(
            f'<p class="case-treatment"><span class="tag">[Descrybe]</span> {rv} {tr}</p>'
        )

    try:
        summary = dscb.summary(case_id)
        summary_html = (
            f'<details><summary><span class="tag">[Descrybe]</span> Case summary</summary>'
            f'<div class="summary-body">{_paragraphs(summary)}</div></details>'
        )
    except Exception:
        summary_html = _needs_verification("case summary")

    try:
        from . import web
        passage = web.case_passages(dscb, case_id, seed)
        passage_html = (
            f'<div class="on-issue"><p><span class="tag">[Descrybe]</span> On this issue</p>'
            f'<div class="passage-body">{_paragraphs(passage)}</div></div>'
        )
    except Exception:
        passage_html = _needs_verification("issue-focused passage")

    try:
        status = dscb.status(case_id)
        status_html = (
            f'<p class="status"><span class="tag">[Descrybe]</span> Status screening '
            f'(a screening signal, not a citator conclusion): {_esc(status)}</p>'
        )
    except Exception:
        status_html = _needs_verification("status screening")

    return (
        '<section class="case-entry">'
        + "".join(header)
        + summary_html
        + passage_html
        + status_html
        + "</section>"
    )


def _foundational_block(nodes):
    if not nodes:
        return "<p><em>No foundational candidates identified.</em></p>"
    items = []
    for n in nodes:
        name = _esc(n["name"])
        date = _esc(n.get("date") or "?")
        cited_by = n.get("cited_by_corpus", 0)
        items.append(
            f"<li>{name} ({date}) &mdash; cited by {cited_by} corpus member(s) "
            f'<span class="tag">[CourtListener]</span></li>'
        )
    return "<ul>" + "".join(items) + "</ul>"


def _cautions_block(nodes):
    cautioned = [n for n in nodes if (n.get("treatment") or "").strip()]
    if not cautioned:
        return "<p><em>No treatment cautions surfaced for corpus cases.</em></p>"
    items = []
    for n in cautioned:
        items.append(
            f'<li>{_esc(n["name"])} &mdash; <span class="tag">[Descrybe]</span> '
            f"{_esc(n['treatment'])}</li>"
        )
    return "<ul>" + "".join(items) + "</ul>"


CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
       margin: 0; background: #fafafa; color: #222; }
header { padding: 1rem 1.2rem; background: #fff; border-bottom: 1px solid #ddd; }
header h1 { font-size: 1.3rem; margin: 0 0 0.3rem; }
header p { margin: 0.15rem 0; font-size: 0.85rem; color: #555; }
header .note { font-style: italic; color: #888; }
main { max-width: 860px; margin: 0 auto; padding: 1rem 1.2rem 3rem; }
h2 { font-size: 1.05rem; border-bottom: 2px solid #4a90d9; padding-bottom: 0.2rem; margin-top: 2rem; }
h3 { font-size: 1rem; margin: 1.4rem 0 0.3rem; }
.case-entry { border: 1px solid #ddd; border-radius: 6px; padding: 0.8rem 1rem; margin: 0.8rem 0; background: #fff; }
.case-meta { font-size: 0.82rem; color: #555; }
.case-treatment { font-size: 0.85rem; }
.tag { display: inline-block; background: #eef; color: #446; font-size: 0.7rem;
       padding: 0.1rem 0.35rem; border-radius: 3px; margin-right: 0.3rem; }
.summary-body, .passage-body { font-size: 0.85rem; max-height: 40vh; overflow-y: auto;
       border-top: 1px dashed #ddd; margin-top: 0.4rem; padding-top: 0.4rem; }
.summary-body p, .passage-body p { margin: 0.5rem 0; }
.on-issue { margin-top: 0.6rem; }
.status { font-size: 0.85rem; margin-top: 0.6rem; }
.nv { color: #a05; font-size: 0.85rem; font-style: italic; }
details summary { cursor: pointer; font-weight: 600; }
ul { font-size: 0.88rem; padding-left: 1.2rem; }
.terms-list { font-size: 0.85rem; }
footer { border-top: 1px solid #ddd; margin-top: 2rem; padding: 1rem 1.2rem; font-size: 0.78rem; color: #666; }
footer .legend div { margin: 0.1rem 0; }
"""


def build_dossier_html(state, dscb, corpus_mod, top_n=8, download=False):
    """Server-rendered, self-contained HTML dossier document for the current
    corpus in `state` (web.STATE shape). No network calls beyond the per-case
    Descrybe lookups already required; no external requests are embedded in
    the output. `download` is accepted for symmetry with export call sites
    but does not change the HTML -- Content-Disposition is a response header
    set by the caller, not part of the document body."""
    corpus = state["corpus"]
    if corpus is None:
        raise ValueError("no corpus built")

    seed = state.get("seed") or "(no seed)"
    jurisdiction = state.get("jurisdiction") or "(none specified)"
    now = datetime.now().astimezone().isoformat()
    # only terms the user actually included at corpus build -- searches that
    # were run but excluded must not appear (fallback: node provenance)
    terms = sorted(state.get("included_terms")
                   or {t for n in corpus["nodes"].values() for t in n.get("sources", ())})

    ranked = corpus_mod.rank(corpus)
    leading = [n for n in ranked if n.get("search_membership", 0) > 0][:top_n]
    found = corpus_mod.foundational(ranked)
    found_sorted = sorted(found, key=lambda n: n.get("date") or "9999")

    terms_html = (
        "<ul class=\"terms-list\">" + "".join(f"<li>{_esc(t)}</li>" for t in terms) + "</ul>"
        if terms else "<p><em>no search terms recorded</em></p>"
    )

    leading_html = (
        "".join(_case_block(n, dscb, seed) for n in leading)
        if leading else "<p><em>No issue-relevant leading cases in the current corpus.</em></p>"
    )

    found_html = _foundational_block(found_sorted)
    cautions_html = _cautions_block(ranked)

    n_nodes = len(corpus["nodes"])
    n_edges = len(corpus["edges"])
    n_searches = len(terms)

    doc = f"""<!doctype html>
<html>
<!-- descrybe-constellation issue dossier -- seed: {_esc(seed)} -- generated: {now} --
     Assembled, not generated: every block below is retrieved API text with a
     source label. No LLM authored any sentence in this document. -->
<head>
<meta charset="utf-8">
<title>Issue dossier: {_esc(seed)}</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <h1>Issue dossier &mdash; {_esc(seed)}</h1>
  <p>Jurisdiction: {_esc(jurisdiction)}</p>
  <p>Research current through: {now}</p>
  <p class="note">{REVIEW_NOTE}</p>
  <p>Included search terms:</p>
  {terms_html}
</header>
<main>
  <h2>Leading cases</h2>
  {leading_html}

  <h2>Foundational genealogy</h2>
  {found_html}

  <h2>Cautions</h2>
  {cautions_html}
</main>
<footer>
  <p>Corpus: {n_nodes} case(s), {n_edges} edge(s), {n_searches} included search(es).</p>
  <p>Generated: {now}</p>
  <div class="legend">
    <div><span class="tag">[Descrybe]</span> retrieved content (summary, issue passage, status screening)</div>
    <div><span class="tag">[CourtListener]</span> citation-graph numbers (citation counts, in-corpus cites)</div>
    <div class="nv">[Needs verification] &mdash; retrieval failed for that block</div>
  </div>
</footer>
</body>
</html>
"""
    return doc
