"""Unit tests for constellation/anchor.py -- passage parsing, normalization
(including the citation-divergence rules from the feasibility report), and
the exact -> normalized -> fuzzy paragraph-anchoring chain."""

from constellation import anchor

FIXTURE_PASSAGES = """Returned 2 passages.

1. Passage 1
   text: The quick brown fox jumps over the lazy dog.
2. Passage 2
   text: A passage whose text wraps onto a
   continuation line with no 'text:' prefix.
"""


def test_parse_passages_basic_and_continuation():
    passages = anchor.parse_passages(FIXTURE_PASSAGES)
    assert passages == [
        "The quick brown fox jumps over the lazy dog.",
        "A passage whose text wraps onto a continuation line with no 'text:' prefix.",
    ]


def test_parse_passages_empty():
    assert anchor.parse_passages("Returned 0 passages.\n") == []


def test_normalize_quotes_dashes_whitespace_and_case():
    text = "“Hello—world”   has\nextra   whitespace"
    assert anchor.normalize(text) == '"hello-world" has extra whitespace'


def test_normalize_strips_supra_volume_number():
    # Feasibility report Sec 4: Descrybe's extraction drops the volume number
    # right after "supra" ("Green, supra, 10 Cal.3d 616" -> "Green, supra,
    # Cal.3d 616"); normalize() should equalize both forms.
    with_volume = anchor.normalize("Green, supra, 10 Cal.3d 616")
    without_volume = anchor.normalize("Green, supra, Cal.3d 616")
    assert with_volume == without_volume == "green, supra, cal.3d 616"


def test_normalize_leaves_non_supra_volume_numbers_alone():
    assert "10" in anchor.normalize("See 10 Cal.3d 616 (1974).")


def test_normalize_collapses_parallel_citation_run():
    text = "38 Cal.3d 454, 698 P.2d 116, 213 Cal. Rptr. 213"
    normalized = anchor.normalize(text)
    assert normalized == "38 cal.3d 454"


def test_anchor_passage_exact_hit():
    paragraphs = [("p-1", "Tenants may raise the implied warranty of habitability as a defense.")]
    result = anchor.anchor_passage("implied warranty of habitability", paragraphs)
    assert result["status"] == "exact"
    assert result["paragraph_id"] == "p-1"
    assert result["ratio"] == 1.0
    text = paragraphs[0][1]
    assert text[result["char_start"]:result["char_end"]] == "implied warranty of habitability"


def test_anchor_passage_normalized_only_hit():
    # Curly quotes + irregular whitespace only -- no citation divergence.
    passage = "“implied warranty”  of   habitability"
    paragraphs = [("p-1", 'The "implied warranty" of habitability is well established.')]
    result = anchor.anchor_passage(passage, paragraphs)
    assert result["status"] == "normalized"
    assert result["paragraph_id"] == "p-1"
    assert result["char_start"] is None
    assert result["char_end"] is None


def test_anchor_passage_fuzzy_only_hit():
    # Perturbed citation like the feasibility report's Fairchild v. Park
    # example ("Green, supra, Cal.3d 616" vs CourtListener's "Green, supra,
    # 10 Cal.3d 616"). normalize() closes that specific gap on its own (it
    # strips the volume number around "supra"), so to force the fuzzy tier
    # this passage also swaps a couple of words elsewhere in the sentence --
    # normalization can't paper over that, but the overall similarity ratio
    # still clears 0.85.
    passage = ("As established in Green, supra, Cal.3d 616, tenants might "
               "raise this defense at trial.")
    paragraphs = [("p-1", "In this jurisdiction, as established in Green, supra, "
                          "10 Cal.3d 616, tenants may raise the defense at trial, "
                          "subject to the usual procedural limits.")]
    result = anchor.anchor_passage(passage, paragraphs)
    assert result["status"] == "fuzzy"
    assert result["paragraph_id"] == "p-1"
    assert result["ratio"] >= 0.85
    assert result["char_start"] is None
    assert result["char_end"] is None


def test_anchor_passage_unanchorable():
    paragraphs = [("p-1", "This paragraph is about something else entirely.")]
    result = anchor.anchor_passage(
        "Completely unrelated text about a different legal doctrine altogether.",
        paragraphs,
    )
    assert result["status"] == "unanchorable"
    assert result["paragraph_id"] is None
    assert result["char_start"] is None


def test_anchor_passage_picks_best_matching_paragraph():
    paragraphs = [
        ("p-1", "Nothing relevant here."),
        ("p-2", "The quick brown fox jumps over the lazy dog."),
    ]
    result = anchor.anchor_passage("The quick brown fox jumps over the lazy dog.", paragraphs)
    assert result["status"] == "exact"
    assert result["paragraph_id"] == "p-2"


def test_anchor_passage_empty_passage_or_paragraphs():
    assert anchor.anchor_passage("", [("p-1", "text")])["status"] == "unanchorable"
    assert anchor.anchor_passage("text", [])["status"] == "unanchorable"
