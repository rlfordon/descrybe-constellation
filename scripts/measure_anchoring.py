"""Case-reader anchoring feasibility measurement (docs/research/2026-07-24-case-reader-feasibility.md).

Question: can each Descrybe issue-focused passage (get_case_passages) be
located inside the corresponding CourtListener opinion text, given the two
vendors' independent text pipelines (OCR drift, whitespace, citation
formatting)?

Uses the repo's own modules (Cache, CourtListener, Descrybe, bridge) so every
remote call is cached in data/cache.sqlite -- reruns cost nothing. Never
prints env values; loads .env via the same pattern as scripts/build_corpus.py
and constellation/web.py.

Run:
    .venv/bin/python scripts/measure_anchoring.py

Rerun on a different corpus by editing SEED / JURISDICTION below, or by
importing measure_case() / load_case_set() into another driver script.
"""

import html
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from constellation import bridge
from constellation.anchor import FUZZY_THRESHOLD, fuzzy_locate, normalize, parse_passages
from constellation.cache import Cache
from constellation.cl import CourtListener
from constellation.dscb import Descrybe

TOKEN_NAMES = ["COURTLISTENER_API_TOKEN", "CL_API_TOKEN", "COURTLISTENER_TOKEN"]

SEED = "implied warranty of habitability defense to eviction"
JURISDICTION = "California"

# CourtListener opinion text fields, in preference order for "best available
# full text." html_with_citations is what the availability scan below found
# non-empty on all 15 opinion rows across the 8-case test set; the others
# are checked and reported but not all populated.
TEXT_FIELDS = ["plain_text", "html", "html_with_citations", "html_lawbox", "xml_harvard"]
PRIMARY_FIELD = "html_with_citations"


def load_env():
    env = REPO / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))


# ------------------------------------------------------------- CL opinion text

def opinion_text_fields(cl, opinion_id):
    """All TEXT_FIELDS for one opinion, cached via cl._get (same cached
    session as the rest of the app -- cl.py has no dedicated text method,
    so this calls the private _get directly rather than editing cl.py)."""
    return cl._get(f"opinions/{opinion_id}/", fields="id,type," + ",".join(TEXT_FIELDS))


_TAG_RE = re.compile(r"<[^>]+>")


def html_to_text(markup):
    """Tags -> single space (avoids word concatenation across tag
    boundaries), then HTML-entity unescape. No structure preserved --
    this is the 'plain_text + computed offsets' baseline, not a renderer."""
    if not markup:
        return ""
    return html.unescape(_TAG_RE.sub(" ", markup))


# parse_passages, normalize, and fuzzy_locate now live in constellation/
# anchor.py (imported above) -- factored out so the live case-reader
# (constellation/reader.py) shares this exact implementation rather than
# re-inventing it. Behavior unchanged from what produced the measured/gated
# numbers in docs/research/2026-07-24-case-reader-feasibility.md.


# ------------------------------------------------------------------ per-case

def case_text_availability(cl, cluster_id):
    """Per-opinion field sizes for a cluster's sub_opinions, plus the
    concatenated PRIMARY_FIELD text (tags stripped) used for anchoring."""
    opinion_ids = cl.opinion_ids(cluster_id)
    per_opinion, texts = [], []
    for oid in opinion_ids:
        data = opinion_text_fields(cl, oid)
        sizes = {f: len(data.get(f) or "") for f in TEXT_FIELDS}
        per_opinion.append({"opinion_id": oid, "sizes": sizes})
        texts.append(data.get(PRIMARY_FIELD) or "")
    full_text = html_to_text("\n\n".join(texts))
    return opinion_ids, per_opinion, full_text


def measure_case(cl, dscb, case_id, name, focus):
    cluster_id = bridge.to_cluster_id(case_id)
    opinion_ids, per_opinion, full_text = case_text_availability(cl, cluster_id)
    full_norm = normalize(full_text)

    raw = dscb._text("get_case_passages", {"case_id": case_id, "focus": focus})
    passages = parse_passages(raw)

    rows = []
    for i, p in enumerate(passages, 1):
        p_norm = normalize(p)
        exact = p in full_text
        normalized = (not exact) and (p_norm in full_norm)
        fuzzy_ratio, fuzzy_ok = (None, False)
        if not (exact or normalized):
            fuzzy_ratio, fuzzy_ok = fuzzy_locate(p_norm, full_norm)
        tier = "exact" if exact else "normalized" if normalized else "fuzzy" if fuzzy_ok else "unanchorable"
        rows.append({
            "index": i, "text": p, "len": len(p), "tier": tier,
            "fuzzy_ratio": fuzzy_ratio,
        })

    return {
        "case_id": case_id, "cluster_id": cluster_id, "name": name,
        "opinion_ids": opinion_ids, "per_opinion": per_opinion,
        "full_text_len": len(full_text),
        "passage_rows": rows,
    }


def summarize(case_result):
    rows = case_result["passage_rows"]
    n = len(rows)
    if n == 0:
        return {"n": 0}
    exact = sum(1 for r in rows if r["tier"] == "exact")
    norm_or_better = exact + sum(1 for r in rows if r["tier"] == "normalized")
    fuzzy_or_better = norm_or_better + sum(1 for r in rows if r["tier"] == "fuzzy")
    unanchorable = n - fuzzy_or_better
    return {
        "n": n, "exact": exact, "norm_or_better": norm_or_better,
        "fuzzy_or_better": fuzzy_or_better, "unanchorable": unanchorable,
        "exact_pct": 100 * exact / n,
        "normalized_pct": 100 * norm_or_better / n,
        "fuzzy_pct": 100 * fuzzy_or_better / n,
    }


# ------------------------------------------------------------------------ main

def main():
    load_env()
    cache = Cache(REPO / "data" / "cache.sqlite")
    token = next((os.environ[n] for n in TOKEN_NAMES if os.environ.get(n)), None)
    if not token:
        sys.exit(f"need a CourtListener token in .env ({TOKEN_NAMES})")
    cl = CourtListener(token, cache)
    dscb = Descrybe(cache)

    print(f"== seed search: {SEED!r} / {JURISDICTION} ==")
    entries = dscb.search(SEED, JURISDICTION)
    print(f"search-origin cases: {len(entries)}")
    for e in entries:
        print(f"  {e['case_id']}  {e['name']}")

    print("\n== per-opinion CL text-field availability (chars; 0 = absent) ==")
    print(f"{'case_id':10} {'cluster_id':10} {'opinion_id':10} " +
          " ".join(f"{f:>18}" for f in TEXT_FIELDS))

    results = []
    for e in entries:
        r = measure_case(cl, dscb, e["case_id"], e["name"], SEED)
        results.append(r)
        for po in r["per_opinion"]:
            print(f"{r['case_id']:10} {r['cluster_id']:<10} {po['opinion_id']:<10} " +
                  " ".join(f"{po['sizes'][f]:>18}" for f in TEXT_FIELDS))

    print(f"\n== anchoring (primary field: {PRIMARY_FIELD}, tag-stripped text; "
          f"fuzzy threshold {FUZZY_THRESHOLD}) ==")
    print(f"{'case_id':10} {'name':40} {'n_pass':>7} {'exact%':>8} "
          f"{'norm%':>8} {'fuzzy%':>8} {'unanch':>7}")

    totals = {"n": 0, "exact": 0, "norm": 0, "fuzzy": 0, "unanch": 0}
    unanchorable_examples = []
    fuzzy_examples = []
    for r in results:
        s = summarize(r)
        if s["n"] == 0:
            print(f"{r['case_id']:10} {r['name'][:40]:40} {'0':>7} {'--':>8} {'--':>8} {'--':>8} {'--':>7}")
            continue
        print(f"{r['case_id']:10} {r['name'][:40]:40} {s['n']:>7} "
              f"{s['exact_pct']:>7.1f}% {s['normalized_pct']:>7.1f}% "
              f"{s['fuzzy_pct']:>7.1f}% {s['unanchorable']:>7}")
        totals["n"] += s["n"]
        totals["exact"] += s["exact"]
        totals["norm"] += s["norm_or_better"]
        totals["fuzzy"] += s["fuzzy_or_better"]
        totals["unanch"] += s["unanchorable"]
        for row in r["passage_rows"]:
            if row["tier"] == "fuzzy":
                fuzzy_examples.append((r["case_id"], r["name"], row))
            elif row["tier"] == "unanchorable":
                unanchorable_examples.append((r["case_id"], r["name"], row))

    if totals["n"]:
        print("\n== totals across all cases ==")
        print(f"passages: {totals['n']}")
        print(f"exact:        {totals['exact']:>3} ({100*totals['exact']/totals['n']:.1f}%)")
        print(f"normalized (cum): {totals['norm']:>3} ({100*totals['norm']/totals['n']:.1f}%)")
        print(f"fuzzy (cum):      {totals['fuzzy']:>3} ({100*totals['fuzzy']/totals['n']:.1f}%)")
        print(f"unanchorable:     {totals['unanch']:>3} ({100*totals['unanch']/totals['n']:.1f}%)")

    if fuzzy_examples:
        print("\n== fuzzy-tier examples (normalized substring failed, 0.85+ window found) ==")
        for cid, name, row in fuzzy_examples:
            print(f"-- {cid} {name} passage#{row['index']} ratio={row['fuzzy_ratio']:.3f}")
            print(f"   {row['text'][:220]}")

    if unanchorable_examples:
        print("\n== unanchorable examples (best fuzzy window < threshold) ==")
        for cid, name, row in unanchorable_examples:
            print(f"-- {cid} {name} passage#{row['index']} best_ratio="
                  f"{row['fuzzy_ratio']:.3f}" if row['fuzzy_ratio'] is not None else "n/a")
            print(f"   {row['text'][:220]}")

    print(f"\ncache: {cache.stats()}")


if __name__ == "__main__":
    main()
