"""End-to-end corpus build from the command line (pre-UI driver).

    .venv/bin/python scripts/build_corpus.py "implied warranty of habitability defense to eviction" \
        --jurisdiction California \
        --variant "habitability defects defense to nonpayment of rent" \
        --variant "tenant remedies uninhabitable premises" \
        --backward --forward

Prints included search clusters, leading cases, and foundational candidates;
writes the corpus (nodes + edges) to data/corpus.json.
"""

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from constellation.cache import Cache
from constellation.cl import CourtListener
from constellation.dscb import Descrybe, issue_labels
from constellation import corpus as C

TOKEN_NAMES = ["COURTLISTENER_API_TOKEN", "CL_API_TOKEN", "COURTLISTENER_TOKEN"]


def load_env():
    env = REPO / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seed")
    ap.add_argument("--jurisdiction")
    ap.add_argument("--variant", action="append", default=[])
    ap.add_argument("--harvest-labels", action="store_true",
                    help="add searches for issue labels found in seed results")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--backward", action="store_true")
    ap.add_argument("--forward", action="store_true")
    ap.add_argument("--forward-cap", type=int, default=10)
    args = ap.parse_args()

    load_env()
    cache = Cache(REPO / "data" / "cache.sqlite")
    token = next((os.environ[n] for n in TOKEN_NAMES if os.environ.get(n)), None)
    if not token:
        sys.exit(f"need a CourtListener token in .env ({TOKEN_NAMES})")
    cl = CourtListener(token, cache)
    dscb = Descrybe(cache)

    terms = [args.seed] + args.variant
    results = {t: dscb.search(t, args.jurisdiction) for t in terms}
    if args.harvest_labels:
        for label in issue_labels(results[args.seed]):
            if label not in results:
                results[label] = dscb.search(label, args.jurisdiction)

    clusters = C.cluster_searches(results, args.seed, threshold=args.threshold)
    print("== Search clusters ==")
    for c in clusters:
        mark = "included" if c["included"] else "excluded"
        print(f"  [{mark}] overlap={c['seed_overlap']:.2f} :: {'; '.join(c['terms'])} "
              f"({len(c['case_ids'])} cases)")

    included = [t for c in clusters if c["included"] for t in c["terms"]]
    corpus = C.build_corpus(results, included)
    print(f"\ncorpus after search hops: {len(corpus['nodes'])} cases")

    if args.backward:
        added = C.expand_backward(corpus, cl)
        print(f"backward hop: +{len(added)} foundational candidates, "
              f"{len(corpus['edges'])} edges")
    if args.forward:
        added, notes = C.expand_forward(corpus, cl, per_node_cap=args.forward_cap)
        print(f"forward hop: +{len(added)} citing cases, {len(corpus['edges'])} edges")
        for n in notes:
            print(f"  note: {n}")

    ranked = C.rank(corpus)
    print("\n== Leading cases (cited-by-corpus / searches / court weight) ==")
    for n in ranked[:12]:
        print(f"  {n['cited_by_corpus']:>3} / {n['search_membership']} / {n['court_weight']}"
              f"  {n['name']}  ({n.get('court') or '?'}; {n.get('date') or '?'})"
              f"  [{n['origin']}]")

    badges = C.foundational(ranked)
    if badges:
        print("\n== Foundational candidates (absent from searches, pre-median, multiply cited) ==")
        for n in badges:
            print(f"  {n['name']} ({n.get('date')}) cited by {n['cited_by_corpus']} corpus members")

    out = REPO / "data" / "corpus.json"
    out.write_text(json.dumps(
        {"nodes": {str(k): dict(v, sources=sorted(v["sources"])) for k, v in corpus["nodes"].items()},
         "edges": sorted(corpus["edges"])}, indent=2))
    print(f"\nwrote {out.relative_to(REPO)} | cache: {cache.stats()}")


if __name__ == "__main__":
    main()
