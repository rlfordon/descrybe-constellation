"""Web app tests: FakeDescrybe/FakeCL stand in for the live APIs -- no live
calls here (see docs/design.md and the build brief). Covers the
search -> clusters -> corpus -> graph flow, a backward hop, and both exports.
"""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constellation import web
from constellation.dscb import parse_entries

FIXTURE = (Path(__file__).parent / "fixtures" / "search_sample.txt").read_text()
FIXTURE_ENTRIES = parse_entries(FIXTURE)


class FakeDescrybe:
    """Every search returns the two fixture cases (Green / Stoiber)."""

    def search(self, term, jurisdiction=None, sort="authority"):
        return FIXTURE_ENTRIES

    def citers(self, case_id):
        return []

    def summary(self, case_id):
        return "Fake summary: this case discusses the implied warranty of habitability."

    def details(self, case_id):
        return "Fake case details."

    def status(self, case_id):
        return "Fake status: no negative treatment found."

    def _text(self, tool, args):
        # web.case_passages calls this private method directly (dscb.py has
        # no get_case_passages wrapper); the fake mirrors that contract.
        if tool == "get_case_passages":
            return f"Fake passage for {args.get('case_id')} on '{args.get('focus')}'."
        raise RuntimeError(f"unexpected tool {tool!r}")


class FakeCL:
    """Both fixture clusters (1182285, 2134128) cite one shared outside
    opinion -- exercises the backward hop's foundational-candidate path."""

    _OPINION = {1182285: 11822850, 2134128: 21341280}
    _OUTSIDE_OPINION = 9999900
    _OUTSIDE_CLUSTER = 999900

    def opinion_ids(self, cluster_id):
        return [self._OPINION[cluster_id]]

    def cited_opinions(self, opinion_id):
        if opinion_id in self._OPINION.values():
            return [self._OUTSIDE_OPINION]
        return []

    def cluster_id_of_opinion(self, opinion_id):
        assert opinion_id == self._OUTSIDE_OPINION
        return self._OUTSIDE_CLUSTER

    def cluster(self, cluster_id):
        assert cluster_id == self._OUTSIDE_CLUSTER
        return {"id": cluster_id, "case_name": "Foundational Case",
                "date_filed": "1900-01-01", "citation_count": 500}

    def citing_clusters(self, opinion_id, max_pages=3):
        return [], 0, False


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    web.STATE = web.new_state()
    monkeypatch.setattr(web, "get_descrybe", lambda: FakeDescrybe())
    monkeypatch.setattr(web, "get_cl", lambda: FakeCL())
    yield


@pytest.fixture
def client():
    return TestClient(web.app)


def test_search_clusters_corpus_graph_flow(client):
    r = client.post("/api/search", json={
        "seed": "implied warranty of habitability",
        "variants": ["habitability defects defense to nonpayment of rent"],
        "harvest_labels": True,
        "threshold": 0.5,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["clusters"]
    included_terms = [t for c in body["clusters"] if c["included"] for t in c["terms"]]
    assert included_terms

    r = client.post("/api/corpus", json={"included_terms": included_terms})
    assert r.status_code == 200
    graph = r.json()
    assert len(graph["nodes"]) == 2
    case_ids = {n["case_id"] for n in graph["nodes"]}
    assert case_ids == {"c1182285", "c2134128"}

    r = client.get("/api/graph")
    assert r.status_code == 200
    assert len(r.json()["nodes"]) == 2

    r = client.get("/api/case/c1182285")
    assert r.status_code == 200
    assert "habitability" in r.json()["summary"].lower()

    r = client.get("/api/case/c1182285?focus=habitability")
    assert r.status_code == 200
    assert "passage" in r.json()


def test_expand_backward_adds_foundational_candidate(client):
    client.post("/api/search", json={"seed": "seed term", "variants": [], "threshold": 0.5})
    client.post("/api/corpus", json={"included_terms": ["seed term"]})

    r = client.post("/api/expand", json={"direction": "backward"})
    assert r.status_code == 200
    graph = r.json()
    assert len(graph["nodes"]) == 3
    assert any(n["origin"] == "backward" for n in graph["nodes"])
    assert graph["foundational"]
    assert graph["foundational"][0]["cluster_id"] == FakeCL._OUTSIDE_CLUSTER


def test_expand_requires_corpus_first(client):
    r = client.post("/api/expand", json={"direction": "backward"})
    assert r.status_code == 400


def test_trail_export_has_seed_and_courtlistener_tag(client):
    client.post("/api/search", json={"seed": "eviction habitability defense", "variants": []})
    client.post("/api/corpus", json={"included_terms": ["eviction habitability defense"]})
    client.post("/api/expand", json={"direction": "backward"})

    r = client.get("/api/export/trail")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    text = r.text
    assert "eviction habitability defense" in text
    assert "[CourtListener]" in text


def test_snapshot_export_embeds_graph_and_has_no_stray_urls(client):
    client.post("/api/search", json={"seed": "eviction habitability defense", "variants": []})
    client.post("/api/corpus", json={"included_terms": ["eviction habitability defense"]})

    r = client.get("/api/export/snapshot")
    assert r.status_code == 200
    html = r.text
    assert '<script id="graph-data" type="application/json">' in html
    assert '"c1182285"' in html or "c1182285" in html

    # No external requests: strip the inlined vendor script (its license
    # header legitimately mentions a couple of http:// URLs as text) and
    # confirm nothing outside it references an external resource.
    stripped = re.sub(
        r'<script id="cytoscape-vendor">.*?</script>', "", html, flags=re.S
    )
    assert "http://" not in stripped
    assert "https://" not in stripped
