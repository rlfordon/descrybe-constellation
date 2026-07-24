from pathlib import Path

from constellation.dscb import parse_entries, parse_counts, issue_labels

FIXTURE = (Path(__file__).parent / "fixtures" / "search_sample.txt").read_text()


def test_parse_entries_fields():
    entries = parse_entries(FIXTURE)
    assert len(entries) == 2
    green, stoiber = entries
    assert green["case_id"] == "c1182285"
    assert green["name"] == "Green v. Superior Court"
    assert green["court"] == "California Supreme Court"
    assert green["date"] == "1974-01-15"
    assert green["research_value"].startswith("Leading authority")
    assert green["treatment"] is None
    assert stoiber["case_id"] == "c2134128"
    assert "cautionary treatment" in stoiber["treatment"]


def test_wrapped_field_continuation():
    stoiber = parse_entries(FIXTURE)[1]
    assert "not one of the strongest matches" in stoiber["research_value"]
    assert stoiber["snippet"].endswith("offset due rent.")


def test_counts_and_labels():
    assert parse_counts(FIXTURE) == (15, 2)
    assert issue_labels(parse_entries(FIXTURE)) == ["Implied Warranty of Habitability"]
