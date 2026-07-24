from constellation import corpus


def entries(*ids):
    return [{"case_id": f"c{i}", "name": f"Case {i}", "court": None, "date": None,
             "research_value": None, "treatment": None} for i in ids]


def test_cluster_searches_opt_out():
    results = {
        "seed": entries(1, 2, 3, 4),
        "near-dupe": entries(1, 2, 3, 5),        # high overlap -> auto-included
        "distinct": entries(10, 11, 12),          # no overlap -> excluded
    }
    clusters = corpus.cluster_searches(results, "seed", threshold=0.5)
    by_first = {c["terms"][0]: c for c in clusters}
    assert by_first["seed"]["included"]
    assert "near-dupe" in by_first["seed"]["terms"]  # merged into seed cluster
    assert not by_first["distinct"]["included"]


class FakeCL:
    """cluster 1 & 2 in corpus; both cite outside opinion 900 (cluster 90);
    cluster 2 also cites cluster 1."""
    def opinion_ids(self, cluster_id):
        return {1: [100], 2: [200], 90: [900]}[cluster_id]

    def cited_opinions(self, opinion_id):
        return {100: [900], 200: [900, 100], 900: []}[opinion_id]

    def cluster_id_of_opinion(self, opinion_id):
        return {900: 90}[opinion_id]

    def cluster(self, cluster_id):
        return {"id": cluster_id, "case_name": f"Foundation {cluster_id}",
                "date_filed": "1900-01-01", "citation_count": 500}


def test_backward_expansion_and_foundational_badge():
    results = {"seed": [
        dict(e, date="1980-01-01", court="State Supreme Court")
        for e in entries(1, 2)
    ]}
    c = corpus.build_corpus(results, ["seed"])
    added = corpus.expand_backward(c, FakeCL(), min_shared_citers=2)
    assert added == [90]
    assert (2, 1) in c["edges"]          # in-corpus edge found
    assert (1, 90) in c["edges"] and (2, 90) in c["edges"]

    ranked = corpus.rank(c)
    assert ranked[0]["cluster_id"] == 90  # cited by both members
    assert ranked[0]["cited_by_corpus"] == 2
    badges = corpus.foundational(ranked)
    assert [b["cluster_id"] for b in badges] == [90]


def test_rank_is_explainable_tuple_sort():
    results = {"a": entries(1, 2), "b": entries(2)}
    c = corpus.build_corpus(results, ["a", "b"])
    ranked = corpus.rank(c)
    assert ranked[0]["cluster_id"] == 2   # membership 2 beats 1 when no edges
    assert ranked[0]["search_membership"] == 2
    assert ranked[0]["cited_by_corpus"] == 0


def test_court_level_mapping():
    assert corpus.court_level("Supreme Court of the United States") == "high"
    assert corpus.court_level("California Supreme Court") == "high"
    assert corpus.court_level("United States Court of Appeals for the Ninth Circuit") == "appellate"
    assert corpus.court_level("California Court of Appeal") == "appellate"
    assert corpus.court_level("New York Appellate Division") == "appellate"
    assert corpus.court_level("United States District Court for the Northern District of California") == "trial"
    assert corpus.court_level("Superior Court of California, County of Los Angeles") == "trial"
    assert corpus.court_level("Los Angeles Municipal Court") == "trial"
    assert corpus.court_level(None) == "unknown"
    assert corpus.court_level("Some Administrative Tribunal") == "unknown"


class FakeCLCourts:
    """court_of_cluster/cluster stand-in for enrich_nodes tests."""

    def court_of_cluster(self, cluster_id):
        return {"court": "California Court of Appeal", "court_id": "calctapp"}

    def cluster(self, cluster_id):
        return {"citation_count": 42}


def test_enrich_nodes_backfills_court_and_citation_count():
    results = {"seed": entries(1, 2)}
    c = corpus.build_corpus(results, ["seed"])
    c["nodes"][1]["court"] = None                # simulate a backward node missing court
    c["nodes"][2]["citeCount"] = 7                # simulate a forward node's raw field
    c["nodes"][2]["origin"] = "forward"

    corpus.enrich_nodes(c, FakeCLCourts())

    assert c["nodes"][1]["court"] == "California Court of Appeal"
    assert c["nodes"][1]["court_level"] == "appellate"
    assert c["nodes"][1]["citation_count"] == 42   # search-origin, backfilled via cluster()
    assert c["nodes"][2]["citation_count"] == 7     # forward citeCount normalized
    assert c["nodes"][2]["court_level"] == "appellate"  # court was also None -> backfilled


def test_enrich_nodes_survives_lookup_failure():
    class BrokenCL:
        def court_of_cluster(self, cluster_id):
            raise RuntimeError("network down")

        def cluster(self, cluster_id):
            raise RuntimeError("network down")

    results = {"seed": entries(1)}
    c = corpus.build_corpus(results, ["seed"])
    c["nodes"][1]["court"] = None
    corpus.enrich_nodes(c, BrokenCL())            # must not raise
    assert c["nodes"][1]["court"] is None
    assert c["nodes"][1]["court_level"] == "unknown"
