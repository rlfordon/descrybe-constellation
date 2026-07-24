"""Discovery spike (design.md §8): real calls against both APIs, raw payloads
saved to spike_output/ for inspection. Run sections independently:

    .venv/bin/python scripts/spike.py cl        # CourtListener: lookup, opinions_cited, cites:
    .venv/bin/python scripts/spike.py descrybe  # Descrybe: legal_issue search, summaries, citers
    .venv/bin/python scripts/spike.py bridge    # ID mapping: Descrybe results -> CL opinion IDs

Requires: COURTLISTENER token in .env (several names accepted, see TOKEN_NAMES)
and a completed `dle login` for the descrybe/bridge sections.
"""

import json
import os
import sys
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "spike_output"
CL_BASE = "https://www.courtlistener.com/api/rest/v4"
TOKEN_NAMES = ["COURTLISTENER_API_TOKEN", "CL_API_TOKEN", "COURTLISTENER_TOKEN"]

# Seed topic for the whole spike — well-charted doctrine with a known anchor
# case, so payload shapes are easy to sanity-check by hand.
SEED_ISSUE = "implied warranty of habitability defense to eviction"
SEED_JURISDICTION = "California"
KNOWN_CITATION = {"volume": "10", "reporter": "Cal. 3d", "page": "616"}  # Green v. Superior Court


def load_env():
    env = REPO / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def cl_token():
    for name in TOKEN_NAMES:
        if os.environ.get(name):
            print(f"[cl] using token from ${name} (value not shown)")
            return os.environ[name]
    sys.exit(f"[cl] no CourtListener token found; expected one of {TOKEN_NAMES} in .env")


def save(name, payload):
    OUT.mkdir(exist_ok=True)
    path = OUT / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2, default=str))
    print(f"[saved] {path.relative_to(REPO)}")


def cl_get(session, path, **params):
    r = session.get(f"{CL_BASE}/{path}", params=params, timeout=60)
    print(f"[cl] GET {path} params={params} -> {r.status_code}")
    r.raise_for_status()
    return r.json()


def spike_cl():
    s = requests.Session()
    s.headers["Authorization"] = f"Token {cl_token()}"

    # Q3 groundwork: citation-lookup on the known anchor.
    lookup = s.post(f"{CL_BASE}/citation-lookup/", data={"text": "10 Cal. 3d 616"}, timeout=60)
    print(f"[cl] POST citation-lookup -> {lookup.status_code}")
    lookup.raise_for_status()
    save("cl_citation_lookup", lookup.json())

    clusters = lookup.json()[0].get("clusters", []) if lookup.json() else []
    if not clusters:
        print("[cl] lookup returned no clusters; stopping CL section early")
        return
    cluster_id = clusters[0]["id"]
    cluster = cl_get(s, f"clusters/{cluster_id}/", fields="id,case_name,sub_opinions,citation_count,date_filed")
    save("cl_cluster", cluster)

    opinion_url = cluster["sub_opinions"][0]
    opinion_id = int(str(opinion_url).rstrip("/").rsplit("/", 1)[-1])

    # Q4a: backward edges — the table of authorities.
    opinion = cl_get(s, f"opinions/{opinion_id}/", fields="id,opinions_cited,author_str,type")
    save("cl_opinion_backward", opinion)
    print(f"[cl] opinions_cited count: {len(opinion.get('opinions_cited', []))}")

    # Q4b: forward edges — cites: search, opinion IDs per convention.
    fwd = cl_get(s, "search/", q=f"cites:({opinion_id})", type="o",
                 fields="caseName,dateFiled,cluster_id,court")
    save("cl_forward_cites", fwd)
    print(f"[cl] forward citers reported: {fwd.get('count')}")


def descrybe_client():
    from descrybe_legal_engine import LegalEngine
    return LegalEngine.from_token_store()  # local single-user profile from `dle login`


def spike_descrybe():
    eng = descrybe_client()

    # Q1: related-issues payload + current duplication behavior.
    issue = eng.call_tool("search_cases_by_concept", {
        "term": SEED_ISSUE, "jurisdiction": SEED_JURISDICTION,
        "sort": "authority", "search_focus": "legal_issue",
    })
    save("descrybe_issue_search", issue)

    # Q5: plain concept search for result-set size comparison.
    general = eng.call_tool("search_cases_by_concept", {
        "term": SEED_ISSUE, "jurisdiction": SEED_JURISDICTION,
    })
    save("descrybe_general_search", general)

    # Q2: citer payload; case details for the citation strings the bridge needs.
    # Payload shape is unknown pre-spike, but case_id shape is documented
    # (c\d+), so pull the first one out of the raw JSON.
    import re
    ids = re.findall(r'"(c\d{4,})"', json.dumps(issue))
    if not ids:
        sys.exit("[descrybe] no case_id found in issue-search payload; inspect spike_output/descrybe_issue_search.json")
    case_id = ids[0]
    print(f"[descrybe] using case_id {case_id} for detail calls")
    for tool, name in [("get_case_details", "descrybe_case_details"),
                       ("get_case_summary", "descrybe_case_summary"),
                       ("find_cases_that_cite", "descrybe_citers")]:
        save(name, eng.call_tool(tool, {"case_id": case_id}))


def spike_bridge():
    """Q3: map every case in the saved Descrybe search to a CL opinion ID via
    its citation string; report hit-rate. Run after `cl` and `descrybe`."""
    details = json.loads((OUT / "descrybe_issue_search.json").read_text())
    s = requests.Session()
    s.headers["Authorization"] = f"Token {cl_token()}"
    # Payload shape unknown until the descrybe section runs — this section is
    # finished by hand against spike_output/descrybe_issue_search.json.
    print("[bridge] inspect spike_output/descrybe_issue_search.json and adapt "
          "the citation extraction below, then re-run.")
    save("bridge_placeholder", {"todo": "wire citation strings -> POST citation-lookup/", "have_results": bool(details)})


if __name__ == "__main__":
    load_env()
    section = sys.argv[1] if len(sys.argv) > 1 else "cl"
    {"cl": spike_cl, "descrybe": spike_descrybe, "bridge": spike_bridge}[section]()
