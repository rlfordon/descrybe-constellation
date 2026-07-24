"""constellation/reader.py: sanitizer + build_reader tests. No live calls --
FakeCL/FakeDescrybe stand in for the real APIs, same convention as
tests/test_web.py."""

import re

from constellation import reader


# ------------------------------------------------------------------ sanitizer

def test_sanitizer_strips_script_style_iframe_img_link():
    raw = (
        '<p id="a">keep me<script>alert(1)</script>'
        '<style>.x{color:red}</style>'
        '<iframe src="https://evil.example/x"></iframe>'
        '<img src="https://evil.example/y.png">'
        '<link rel="stylesheet" href="https://evil.example/z.css">'
        "</p>"
    )
    out = reader.sanitize_opinion_html(raw)
    assert "keep me" in out
    assert "alert(1)" not in out
    assert "color:red" not in out
    assert "<script" not in out
    assert "<style" not in out
    assert "<iframe" not in out
    assert "<img" not in out
    assert "<link" not in out
    assert "http://" not in out and "https://" not in out


def test_sanitizer_unwraps_links_and_drops_href():
    raw = '<p id="a">See <a href="https://example.com/opinion">the opinion</a> above.</p>'
    out = reader.sanitize_opinion_html(raw)
    assert "<a" not in out and "</a>" not in out
    assert "the opinion" in out
    assert "http://" not in out and "https://" not in out


def test_sanitizer_strips_event_and_style_attrs_keeps_id_class():
    raw = '<p id="p1" class="foo" onclick="evil()" style="color:red">text</p>'
    out = reader.sanitize_opinion_html(raw)
    assert 'id="p1"' in out
    assert 'class="foo"' in out
    assert "onclick" not in out
    assert "style=" not in out


def test_sanitizer_keeps_allowlisted_inline_tags():
    raw = '<p id="a">The case <em>Green v. Superior Court</em> holds <strong>X</strong>.</p>'
    out = reader.sanitize_opinion_html(raw)
    assert "<em>Green v. Superior Court</em>" in out
    assert "<strong>X</strong>" in out


def test_sanitizer_empty_input():
    assert reader.sanitize_opinion_html("") == ""
    assert reader.sanitize_opinion_html(None) == ""


# --------------------------------------------------------------- build_reader

CANNED_HTML = (
    '<p id="para-1">Tenants may raise the implied warranty of habitability '
    "as a defense to an eviction action.</p>"
    '<p id="para-2">In this jurisdiction, as established in '
    '<em>Green v. Superior Court</em>, supra, 10 Cal.3d 616, tenants may '
    "raise the defense at trial, subject to the usual procedural limits.</p>"
)

# Passage 1: exact substring of para-1's plain text.
# Passage 2: perturbed citation (dropped volume number + reworded tail) --
#   fuzzy-only against para-2, mirroring the feasibility report's citation-
#   divergence pattern (Fairchild v. Park: "Green, supra, Cal.3d 616" vs
#   CourtListener's "Green, supra, 10 Cal.3d 616").
# Passage 3: unrelated text absent from both paragraphs -- unanchorable.
PASSAGES_PAYLOAD = """Returned 3 passages.

1. Passage 1
   text: Tenants may raise the implied warranty of habitability as a defense to an eviction action.
2. Passage 2
   text: As established in Green v. Superior Court, supra, Cal.3d 616, tenants might raise this defense at trial.
3. Passage 3
   text: This is an entirely unrelated passage about a different area of law altogether and shares nothing.
"""


class FakeCL:
    def opinion_ids(self, cluster_id):
        return [111, 222]

    def opinion_html(self, opinion_id):
        # first sub-opinion is empty -- exercises the "try each sub-opinion"
        # resolution order; the second one carries the canned text.
        if opinion_id == 111:
            return None
        return CANNED_HTML


class FakeDescrybe:
    def _text(self, tool, args):
        assert tool == "get_case_passages"
        return PASSAGES_PAYLOAD


def test_build_reader_statuses_and_marks():
    result = reader.build_reader("c1182285", "implied warranty of habitability", FakeCL(), FakeDescrybe())

    assert result["meta"]["opinion_id"] == 222
    assert result["meta"]["field"] == "html_with_citations"
    assert result["meta"]["paragraph_count"] == 2

    by_n = {p["n"]: p for p in result["passages"]}
    assert by_n[1]["status"] == "exact"
    assert by_n[1]["paragraph_id"] == "para-1"
    assert by_n[2]["status"] == "fuzzy"
    assert by_n[2]["paragraph_id"] == "para-2"
    assert by_n[2]["ratio"] >= 0.85
    assert by_n[3]["status"] == "unanchorable"
    assert by_n[3]["paragraph_id"] is None

    assert len(result["unanchored"]) == 1
    assert result["unanchored"][0]["n"] == 3

    html = result["html"]
    assert '<mark class="passage-hit" data-passage="1">' in html
    assert "Tenants may raise the implied warranty of habitability as a defense to an eviction action" in html
    assert 'class="passage-para"' in html
    assert 'data-passage="2"' in html

    # No external requests survive anywhere in the rendered document.
    assert "http://" not in html and "https://" not in html


def test_build_reader_raises_when_no_opinion_text():
    class EmptyCL:
        def opinion_ids(self, cluster_id):
            return [111]

        def opinion_html(self, opinion_id):
            return None

    try:
        reader.build_reader("c1182285", "focus", EmptyCL(), FakeDescrybe())
        assert False, "expected NoOpinionText"
    except reader.NoOpinionText:
        pass


def test_split_segments_synthesizes_ids_when_missing():
    sanitized = reader.sanitize_opinion_html(
        '<p>no id here</p><p id="has-id">already tagged</p>'
    )
    segments = reader._split_segments(sanitized)
    paras = [s for s in segments if s["type"] == "para"]
    assert paras[0]["id"] == "p-1"
    assert paras[1]["id"] == "has-id"
