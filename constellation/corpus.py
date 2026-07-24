"""Corpus engine: search-variant hops, overlap clustering, citation expansion,
and explainable leading-case ranking. UI-independent; all state is plain data.

Node identity is the CourtListener cluster ID (shared namespace, spike F1).
An edge (src, dst) always means "src cites dst"; forward/backward is only the
direction of discovery.
"""

import re

from . import bridge


# ---------------------------------------------------------------- searches

def jaccard(a, b):
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if a | b else 0.0


def cluster_searches(results_by_term, seed_term, threshold=0.5):
    """Group searches whose result sets overlap (Jaccard >= threshold).

    Returns a list of dicts {terms, case_ids, seed_overlap, included} where
    `included` implements the opt-out rule: the seed's cluster is always in;
    other clusters join when their overlap with the seed's results clears the
    threshold. Callers may flip `included` freely (the one-click prune).
    """
    ids = {t: {e["case_id"] for e in entries} for t, entries in results_by_term.items()}
    clusters = []
    for term in results_by_term:
        placed = False
        for c in clusters:
            if any(jaccard(ids[term], ids[t]) >= threshold for t in c["terms"]):
                c["terms"].append(term)
                placed = True
                break
        if not placed:
            clusters.append({"terms": [term]})
    seed_ids = ids.get(seed_term, set())
    for c in clusters:
        c["case_ids"] = sorted(set().union(*(ids[t] for t in c["terms"])))
        c["seed_overlap"] = round(jaccard(set(c["case_ids"]), seed_ids), 3)
        c["included"] = seed_term in c["terms"] or c["seed_overlap"] >= threshold
    return clusters


# ------------------------------------------------------------------ corpus

def build_corpus(results_by_term, included_terms):
    """Corpus dict: {"nodes": {cluster_id: node}, "edges": set((src, dst))}."""
    nodes = {}
    for term in included_terms:
        for e in results_by_term[term]:
            cid = bridge.to_cluster_id(e["case_id"])
            node = nodes.setdefault(cid, {
                "cluster_id": cid, "case_id": e["case_id"], "name": e["name"],
                "court": e.get("court"), "date": e.get("date"),
                "research_value": e.get("research_value"),
                "treatment": e.get("treatment"),
                "sources": set(), "origin": "search",
            })
            node["sources"].add(term)
    return {"nodes": nodes, "edges": set()}


def expand_backward(corpus, cl, min_shared_citers=2):
    """Backward hop: each corpus case's table of authorities.

    Edges among corpus members are always added. Cited cases outside the
    corpus become foundational *candidates* — added as nodes only when cited
    by >= min_shared_citers corpus members (bounds API calls and noise).
    """
    nodes, edges = corpus["nodes"], corpus["edges"]
    opinion_owner = {}       # opinion_id -> citing cluster_id (corpus member)
    outside_citers = {}      # cited opinion_id -> set(citing cluster_ids)
    for cid in list(nodes):
        for oid in cl.opinion_ids(cid):
            opinion_owner[oid] = cid
    known_opinions = dict(opinion_owner)
    for oid, citing_cluster in opinion_owner.items():
        for cited in cl.cited_opinions(oid):
            if cited in known_opinions and known_opinions[cited] != citing_cluster:
                edges.add((citing_cluster, known_opinions[cited]))
            elif cited not in known_opinions:
                outside_citers.setdefault(cited, set()).add(citing_cluster)

    added = []
    for cited_oid, citers in outside_citers.items():
        if len(citers) < min_shared_citers:
            continue
        target_cluster = cl.cluster_id_of_opinion(cited_oid)
        if target_cluster is None:
            continue
        if target_cluster not in nodes:
            meta = cl.cluster(target_cluster)
            node = {
                "cluster_id": target_cluster,
                "case_id": bridge.to_case_id(target_cluster),
                "name": meta.get("case_name"), "court": None,
                "date": meta.get("date_filed"),
                "citation_count": meta.get("citation_count"),
                "research_value": None, "treatment": None,
                "sources": set(), "origin": "backward",
            }
            if node["name"] is not None:
                nodes[target_cluster] = node
                added.append(target_cluster)
        if target_cluster in nodes:
            for citing_cluster in citers:
                edges.add((citing_cluster, target_cluster))
    return added


def expand_forward(corpus, cl, per_node_cap=10, add_new=True,
                   expand_origins=("search",)):
    """Forward hop: later cases citing corpus members, via cites: search.

    Adds edges (citer -> member). New citer nodes are added up to per_node_cap
    per member (ordered as returned — CL relevance), flagged origin="forward".
    Only nodes whose origin is in expand_origins are expanded: by default just
    search results — forward-walking backward-discovered foundations drags in
    their entire (often off-topic) citing universe. Returns
    (added_cluster_ids, truncation_notes).
    """
    nodes, edges = corpus["nodes"], corpus["edges"]
    added, notes = [], []
    for cid in list(nodes):
        if nodes[cid]["origin"] not in expand_origins:
            continue  # chaining further hops is an explicit re-run with wider origins
        for oid in cl.opinion_ids(cid):
            rows, count, truncated = cl.citing_clusters(oid)
            if truncated:
                notes.append(f"{nodes[cid]['name']}: {len(rows)} of {count} citers fetched")
            taken = 0
            for row in rows:
                citer = row.get("cluster_id")
                if citer is None:
                    continue
                if citer in nodes:
                    edges.add((citer, cid))
                elif add_new and taken < per_node_cap:
                    nodes[citer] = {
                        "cluster_id": citer, "case_id": bridge.to_case_id(citer),
                        "name": row.get("caseName"), "court": row.get("court"),
                        "date": (row.get("dateFiled") or "")[:10] or None,
                        "citeCount": row.get("citeCount"),
                        "status": row.get("status"),
                        "research_value": None, "treatment": None,
                        "sources": set(), "origin": "forward",
                    }
                    edges.add((citer, cid))
                    added.append(citer)
                    taken += 1
    return added, notes


# ----------------------------------------------------------------- ranking

_COURT_WEIGHT = [
    (re.compile(r"supreme", re.I), 3),
    (re.compile(r"appel|appeal|circuit", re.I), 2),
]


def court_weight(court_name):
    for pat, w in _COURT_WEIGHT:
        if court_name and pat.search(court_name):
            return w
    return 1


def rank(corpus):
    """Leading cases by explainable signals only. Returns nodes decorated with
    cited_by_corpus / search_membership / court_weight, sorted lexically by
    (cited_by, membership, court weight) — no composite score."""
    nodes, edges = corpus["nodes"], corpus["edges"]
    cited_by = {cid: 0 for cid in nodes}
    for src, dst in edges:
        if src in nodes and dst in nodes:
            cited_by[dst] += 1
    out = []
    for cid, n in nodes.items():
        out.append(dict(n,
                        sources=sorted(n["sources"]),
                        cited_by_corpus=cited_by[cid],
                        search_membership=len(n["sources"]),
                        court_weight=court_weight(n.get("court"))))
    out.sort(key=lambda n: (n["cited_by_corpus"], n["search_membership"],
                            n["court_weight"], n.get("date") or ""), reverse=True)
    return out


def foundational(ranked, min_cited_by=2):
    """Foundational badge: cited by multiple corpus members, decided before the
    corpus median date, and absent from every search result set."""
    dates = sorted(n["date"] for n in ranked if n.get("date") and n["search_membership"])
    if not dates:
        return []
    cutoff = dates[len(dates) // 2]  # ISO strings sort chronologically; no averaging
    return [n for n in ranked
            if n["search_membership"] == 0
            and n["cited_by_corpus"] >= min_cited_by
            and n["origin"] == "backward"
            and (n.get("date") or "9999") < cutoff]
