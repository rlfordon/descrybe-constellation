"""Dossier tests: FakeDescrybe/FakeCL pattern from tests/test_web.py, extended
so one fake case can raise on its summary call (exercises the per-block
try/except -> "[Needs verification]" path) without failing the document.
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
    """Mirrors tests/test_web.py's FakeDescrybe. `raise_for_case` makes
    summary() raise for one case_id, so the dossier's per-case try/except is
    exercised without failing the whole document."""

    def __init__(self, raise_for_case=None):
        self.raise_for_case = raise_for_case

    def search(self, term, jurisdiction=None, sort="authority"):
        return FIXTURE_ENTRIES

    def citers(self, case_id):
        return []

    def summary(self, case_id):
        if case_id == self.raise_for_case:
            raise RuntimeError("summary retrieval failed")
        return "Fake summary: this case discusses the implied warranty of habitability.\n\nSecond paragraph."

    def details(self, case_id):
        return "Fake case details."

    def status(self, case_id):
        return "Fake status: no negative treatment found."

    def _text(self, tool, args):
        if tool == "get_case_passages":
            return f"Fake passage for {args.get('case_id')} on '{args.get('focus')}'."
        raise RuntimeError(f"unexpected tool {tool!r}")


class FakeCL:
    """Both fixture clusters (1182285, 2134128) cite one shared outside
    opinion -- lets tests exercise the backward hop's foundational-candidate
    path so a non-search-origin node is present in the dossier."""

    _OPINION = {1182285: 11822850, 2134128: 21341280}
    _OUTSIDE_OPINION = 9999900
    _OUTSIDE_CLUSTER = 999900

    _CLUSTER_META = {
        1182285: {"id": 1182285, "case_name": "Green v. Superior Court",
                  "date_filed": "1974-01-15", "citation_count": 233},
        2134128: {"id": 2134128, "case_name": "Stoiber v. Honeychuck",
                  "date_filed": "1980-02-05", "citation_count": 94},
        999900: {"id": 999900, "case_name": "Foundational Case",
                 "date_filed": "1900-01-01", "citation_count": 500},
    }

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
        return self._CLUSTER_META[cluster_id]

    def citing_clusters(self, opinion_id, max_pages=3):
        return [], 0, False

    def court_of_cluster(self, cluster_id):
        return {"court": "Fake Trial Court", "court_id": "fake"}

    def match_clusters_by_text(self, cluster_ids, terms):
        return {cid for cid in cluster_ids if cid == self._OUTSIDE_CLUSTER}


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    web.STATE = web.new_state()
    monkeypatch.setattr(web, "get_descrybe", lambda: FakeDescrybe())
    monkeypatch.setattr(web, "get_cl", lambda: FakeCL())
    yield


@pytest.fixture
def client():
    return TestClient(web.app)


def build_corpus_with_foundational(client):
    """search -> corpus -> backward hop, so the corpus has both search-origin
    cases (Green, Stoiber) and one backward-origin foundational candidate."""
    client.post("/api/search", json={
        "seed": "implied warranty of habitability",
        "variants": [],
        "threshold": 0.5,
    })
    client.post("/api/corpus", json={"included_terms": ["implied warranty of habitability"]})
    client.post("/api/expand", json={"direction": "backward"})


def test_dossier_renders_with_seed_tag_and_leading_case(client):
    build_corpus_with_foundational(client)
    r = client.get("/dossier")
    assert r.status_code == 200
    html = r.text
    assert "implied warranty of habitability" in html
    assert "[Descrybe]" in html
    assert "Green v. Superior Court" in html


def test_leading_cases_are_search_origin_only(client):
    build_corpus_with_foundational(client)
    r = client.get("/dossier")
    html = r.text
    leading_section = html.split("Leading cases</h2>")[1].split("Foundational genealogy</h2>")[0]
    assert "Green v. Superior Court" in leading_section
    assert "Stoiber v. Honeychuck" in leading_section
    assert "Foundational Case" not in leading_section

    # the backward-origin case is still surfaced, just not as a "leading case"
    found_section = html.split("Foundational genealogy</h2>")[1].split("Cautions</h2>")[0]
    assert "Foundational Case" in found_section


def test_descrybe_failure_yields_needs_verification_not_exception(client, monkeypatch):
    # override get_descrybe so summary() raises for the Green case specifically
    monkeypatch.setattr(web, "get_descrybe", lambda: FakeDescrybe(raise_for_case="c1182285"))
    client.post("/api/search", json={
        "seed": "implied warranty of habitability", "variants": [], "threshold": 0.5,
    })
    client.post("/api/corpus", json={"included_terms": ["implied warranty of habitability"]})
    r = client.get("/dossier")
    assert r.status_code == 200
    assert "[Needs verification]" in r.text


def test_dossier_requires_corpus_first(client):
    r = client.get("/dossier")
    assert r.status_code == 400


def test_export_dossier_sets_content_disposition(client):
    build_corpus_with_foundational(client)
    r = client.get("/api/export/dossier")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    assert "dossier-" in r.headers["content-disposition"]
    assert ".html" in r.headers["content-disposition"]


def test_dossier_has_no_external_links(client):
    build_corpus_with_foundational(client)
    r = client.get("/dossier")
    html = r.text
    assert "http://" not in html
    assert "https://" not in html
