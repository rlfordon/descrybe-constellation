"""FastAPI web app: search -> corpus -> citation-hop exploration, over the
core library in this package. Single in-memory session (STATE) -- this is a
local single-user tool, not a multi-tenant server.
"""

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import bridge
from . import corpus as C
from .cache import Cache
from .cl import CourtListener
from .dscb import Descrybe, issue_labels

REPO = Path(__file__).resolve().parent.parent
STATIC_DIR = REPO / "static"
VENDOR_JS = REPO / "data" / "vendor" / "cytoscape.min.js"
CACHE_PATH = REPO / "data" / "cache.sqlite"
TOKEN_NAMES = ["COURTLISTENER_API_TOKEN", "CL_API_TOKEN", "COURTLISTENER_TOKEN"]


def load_env():
    """Copy .env into os.environ at runtime; never read or print values (see
    scripts/build_corpus.py -- same pattern, factored out here for reuse)."""
    env = REPO / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def check_vendor_js():
    """Print a one-line instruction if the vendored cytoscape build is missing.
    Never fetched silently -- no CDN dependency at runtime."""
    if not VENDOR_JS.exists():
        print("missing data/vendor/cytoscape.min.js -- run: "
              "curl -o data/vendor/cytoscape.min.js "
              "https://unpkg.com/cytoscape@3.30.2/dist/cytoscape.min.js")


# --------------------------------------------------------------- clients
# Lazy singletons so import-time never touches .env or the network; tests
# monkeypatch these two functions to inject fakes.

_descrybe = None
_cl = None


def get_descrybe():
    global _descrybe
    if _descrybe is None:
        load_env()
        _descrybe = Descrybe(Cache(CACHE_PATH))
    return _descrybe


def get_cl():
    global _cl
    if _cl is None:
        load_env()
        token = next((os.environ[n] for n in TOKEN_NAMES if os.environ.get(n)), None)
        if not token:
            raise RuntimeError(f"need a CourtListener token in .env ({TOKEN_NAMES})")
        _cl = CourtListener(token, Cache(CACHE_PATH))
    return _cl


def case_passages(dscb, case_id, focus):
    """dscb.py has no get_case_passages wrapper (design.md names the tool;
    the discovery spike never exercised it). Call the cached private _text
    bridge directly rather than editing dscb.py, per the build brief."""
    return dscb._text("get_case_passages", {"case_id": case_id, "focus": focus})


# ------------------------------------------------------------------ state

def new_state():
    return {
        "seed": None, "jurisdiction": None,
        "results_by_term": {}, "clusters": [], "corpus": None,
        "trail": [], "notes": [],
    }


STATE = new_state()


def log_trail(action, detail):
    STATE["trail"].append({
        "ts": datetime.now().astimezone().isoformat(),
        "action": action, "detail": detail,
    })


# ----------------------------------------------------------------- graph

def graph_payload():
    """{nodes, edges, ranked_top, foundational} -- the shape GET /api/graph
    and both exports build from."""
    corpus = STATE["corpus"]
    if corpus is None:
        return {"nodes": [], "edges": [], "ranked_top": [], "foundational": []}
    ranked = C.rank(corpus)
    found = C.foundational(ranked)
    found_ids = {n["cluster_id"] for n in found}
    nodes = [{
        "id": n["cluster_id"], "case_id": n["case_id"], "label": n["name"],
        "origin": n["origin"], "court": n.get("court"), "date": n.get("date"),
        "cited_by_corpus": n["cited_by_corpus"],
        "search_membership": n["search_membership"],
        "court_weight": n["court_weight"],
        "foundational": n["cluster_id"] in found_ids,
        "treatment": n.get("treatment"), "research_value": n.get("research_value"),
    } for n in ranked]
    edges = [[src, dst] for src, dst in sorted(corpus["edges"])]
    return {"nodes": nodes, "edges": edges, "ranked_top": ranked[:15], "foundational": found}


# ------------------------------------------------------------------ app

@asynccontextmanager
async def lifespan(app):
    check_vendor_js()
    yield


app = FastAPI(title="descrybe-constellation", lifespan=lifespan)


@app.get("/")
def index():
    return HTMLResponse((STATIC_DIR / "index.html").read_text())


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/vendor/cytoscape.min.js")
def vendor_js():
    if not VENDOR_JS.exists():
        raise HTTPException(404, "cytoscape.min.js not vendored -- see startup log")
    return HTMLResponse(VENDOR_JS.read_text(), media_type="application/javascript")


class SearchRequest(BaseModel):
    seed: str
    jurisdiction: Optional[str] = None
    variants: list = []
    harvest_labels: bool = False
    threshold: float = 0.5


@app.post("/api/search")
def api_search(req: SearchRequest):
    dscb = get_descrybe()
    STATE["seed"] = req.seed
    STATE["jurisdiction"] = req.jurisdiction

    terms = [req.seed] + list(req.variants)
    results = {t: dscb.search(t, req.jurisdiction) for t in terms}
    if req.harvest_labels:
        for label in issue_labels(results[req.seed]):
            if label not in results:
                results[label] = dscb.search(label, req.jurisdiction)

    STATE["results_by_term"] = results
    clusters = C.cluster_searches(results, req.seed, threshold=req.threshold)
    STATE["clusters"] = clusters
    per_term_counts = {t: len(v) for t, v in results.items()}
    log_trail("search", f"seed={req.seed!r} variants={req.variants} "
                         f"harvest_labels={req.harvest_labels} threshold={req.threshold}")
    return {"clusters": clusters, "per_term_counts": per_term_counts}


class CorpusRequest(BaseModel):
    included_terms: list


@app.post("/api/corpus")
def api_corpus(req: CorpusRequest):
    if not STATE["results_by_term"]:
        raise HTTPException(400, "run /api/search first")
    corpus = C.build_corpus(STATE["results_by_term"], req.included_terms)
    STATE["corpus"] = corpus
    log_trail("corpus", f"included_terms={req.included_terms} nodes={len(corpus['nodes'])}")
    return graph_payload()


class ExpandRequest(BaseModel):
    direction: str
    forward_cap: int = 10


@app.post("/api/expand")
def api_expand(req: ExpandRequest):
    if STATE["corpus"] is None:
        raise HTTPException(400, "build corpus first")
    corpus = STATE["corpus"]
    cl = get_cl()
    if req.direction == "backward":
        added = C.expand_backward(corpus, cl)
        notes = []
        log_trail("expand_backward", f"+{len(added)} foundational candidates")
    elif req.direction == "forward":
        added, notes = C.expand_forward(corpus, cl, per_node_cap=req.forward_cap)
        STATE["notes"].extend(notes)
        log_trail("expand_forward", f"+{len(added)} citing cases cap={req.forward_cap}")
    else:
        raise HTTPException(400, "direction must be 'backward' or 'forward'")
    payload = graph_payload()
    payload["truncation_notes"] = notes
    return payload


@app.get("/api/graph")
def api_graph():
    return graph_payload()


@app.get("/api/case/{case_id}")
def api_case(case_id, focus=None):
    dscb = get_descrybe()
    try:
        result = {
            "summary": dscb.summary(case_id),
            "details": dscb.details(case_id),
            "status": dscb.status(case_id),
        }
    except Exception as e:
        raise HTTPException(502, str(e))
    if focus:
        result["passage"] = case_passages(dscb, case_id, focus)
    log_trail("view_case", f"case_id={case_id} focus={focus!r}")
    return result


# --------------------------------------------------------------- exports

def build_trail_markdown():
    seed = STATE["seed"] or "(no seed)"
    now = datetime.now().astimezone().isoformat()
    lines = [
        f"# Research trail: {seed}", "",
        f"Research current through: {now}", "",
        "Review note: research support, not legal advice.", "",
        "## Events", "",
    ]
    for ev in STATE["trail"]:
        lines.append(f"- {ev['ts']} -- **{ev['action']}**: {ev['detail']}")
    lines += ["", "## Leading Cases", ""]

    corpus = STATE["corpus"]
    if corpus is not None:
        ranked = C.rank(corpus)
        lines.append("| Name | Date | Court | Cited-by-corpus [CourtListener] "
                      "| Searches | Research value [Descrybe] |")
        lines.append("|---|---|---|---|---|---|")
        for n in ranked[:15]:
            lines.append(
                f"| {n['name']} | {n.get('date') or ''} | {n.get('court') or ''} "
                f"| {n['cited_by_corpus']} | {n['search_membership']} "
                f"| {(n.get('research_value') or '').replace(chr(10), ' ')} |"
            )
        lines += ["", "## Foundational Candidates", ""]
        found = C.foundational(ranked)
        if found:
            for n in found:
                lines.append(f"- {n['name']} ({n.get('date') or '?'}) "
                              f"-- cited by {n['cited_by_corpus']} corpus members [CourtListener]")
        else:
            lines.append("_none identified._")
    else:
        lines.append("_no corpus built yet._")
    return "\n".join(lines) + "\n"


@app.get("/api/export/trail")
def export_trail():
    return PlainTextResponse(build_trail_markdown(), media_type="text/markdown")


SNAPSHOT_TEMPLATE = """<!doctype html>
<html>
<!-- descrybe-constellation snapshot -- seed: {seed} -- generated: {ts} --
     research support, not legal advice. No external requests: cytoscape.js
     is inlined below and the graph is embedded as static JSON. -->
<head>
<meta charset="utf-8">
<title>descrybe-constellation snapshot: {seed}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         margin: 0; background: #fafafa; color: #222; }}
  header {{ padding: 0.75rem 1rem; background: #fff; border-bottom: 1px solid #ddd; }}
  header h1 {{ font-size: 1.1rem; margin: 0 0 0.2rem; }}
  header p {{ margin: 0.1rem 0; font-size: 0.8rem; color: #666; }}
  #cy {{ width: 100%; height: calc(100vh - 90px); }}
  #info {{ position: fixed; right: 1rem; top: 90px; width: 260px; max-height: 70vh;
          overflow: auto; background: #fff; border: 1px solid #ccc; border-radius: 6px;
          padding: 0.75rem; font-size: 0.85rem; display: none; }}
</style>
</head>
<body>
<header>
  <h1>descrybe-constellation snapshot &mdash; {seed}</h1>
  <p>Research current through: {ts}</p>
  <p>Research support, not legal advice.</p>
</header>
<div id="cy"></div>
<div id="info"></div>
<script id="cytoscape-vendor">
{cyto_js}
</script>
<script id="graph-data" type="application/json">{graph_json}</script>
<script>
(function () {{
  var data = JSON.parse(document.getElementById("graph-data").textContent);
  var colors = {{ search: "#4a90d9", backward: "#d9984a", forward: "#6bbf6b" }};
  var counts = data.nodes.map(function (n) {{ return n.cited_by_corpus || 0; }});
  var max = Math.max(1, Math.max.apply(null, counts.concat([0])));
  function size(n) {{ return 18 + (60 - 18) * ((n.cited_by_corpus || 0) / max); }}

  var elements = data.nodes.map(function (n) {{
    return {{ data: {{ id: String(n.id), label: n.label, node: n }} }};
  }}).concat(data.edges.map(function (e) {{
    return {{ data: {{ source: String(e[0]), target: String(e[1]) }} }};
  }}));

  var cy = cytoscape({{
    container: document.getElementById("cy"),
    elements: elements,
    layout: {{ name: "cose" }},
    style: [
      {{ selector: "node", style: {{
          "background-color": function (ele) {{ return colors[ele.data("node").origin] || "#999"; }},
          "width": function (ele) {{ return size(ele.data("node")); }},
          "height": function (ele) {{ return size(ele.data("node")); }},
          "border-width": function (ele) {{ return ele.data("node").foundational ? 4 : 0; }},
          "border-color": "#7b3fa0",
          "label": "data(label)", "font-size": 8, "color": "#333",
          "text-valign": "bottom", "text-wrap": "ellipsis", "text-max-width": "80px",
      }} }},
      {{ selector: "edge", style: {{
          "width": 1, "line-color": "#bbb", "target-arrow-color": "#bbb",
          "target-arrow-shape": "triangle", "curve-style": "bezier",
      }} }},
    ],
  }});

  cy.on("tap", "node", function (evt) {{
    var n = evt.target.data("node");
    var info = document.getElementById("info");
    info.style.display = "block";
    info.innerHTML = "<b>" + n.label + "</b><br>" +
      (n.court || "") + " &mdash; " + (n.date || "") + "<br>" +
      "origin: " + n.origin + "<br>" +
      "cited-by-corpus: " + n.cited_by_corpus + "<br>" +
      (n.foundational ? "<b>foundational</b><br>" : "");
  }});
}})();
</script>
</body>
</html>
"""


@app.get("/api/export/snapshot")
def export_snapshot():
    check_vendor_js()
    if not VENDOR_JS.exists():
        raise HTTPException(500, "cytoscape.min.js is not vendored; see server startup log")
    cyto_js = VENDOR_JS.read_text()
    payload = graph_payload()
    graph_json = json.dumps({"nodes": payload["nodes"], "edges": payload["edges"]})
    html = SNAPSHOT_TEMPLATE.format(
        seed=escape(STATE["seed"] or "(no seed)"),
        ts=datetime.now().astimezone().isoformat(),
        cyto_js=cyto_js,
        graph_json=graph_json,
    )
    log_trail("export_snapshot", f"nodes={len(payload['nodes'])}")
    return HTMLResponse(html)
