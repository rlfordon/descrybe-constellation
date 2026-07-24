import pytest

from constellation import bridge


def test_round_trip():
    assert bridge.to_cluster_id("c1182285") == 1182285
    assert bridge.to_case_id(1182285) == "c1182285"


def test_rejects_non_descrybe_ids():
    for bad in ["1182285", "cx12", "opinion/123", ""]:
        with pytest.raises(ValueError):
            bridge.to_cluster_id(bad)


def test_names_match_variants():
    assert bridge.names_match("Erlach v. Sierra Asset Servicing",
                              "Erlach v. Sierra Asset Servicing, LLC")
    assert bridge.names_match("Green v. Superior Court", "GREEN v. SUPERIOR COURT")
    assert bridge.names_match("Peterson v. Superior Court",
                              "Peterson v. Superior Court of Los Angeles")
    assert not bridge.names_match("Green v. Superior Court", "Stoiber v. Honeychuck")
