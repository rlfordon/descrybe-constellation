"""Passage-to-opinion-text anchoring library (docs/research/
2026-07-24-case-reader-feasibility.md and its "Second-corpus validation"
addendum). Factored out of scripts/measure_anchoring.py -- parse_passages,
normalize, and fuzzy_locate are the same functions that produced the
measured/gated numbers, moved here so both the measurement script and the
live reader (constellation/reader.py) share one implementation. Pure text
functions only -- no HTML awareness; callers hand in plain-text paragraphs.
"""

import difflib
import re

FUZZY_THRESHOLD = 0.85


# ------------------------------------------------------------ passage parsing

_PASSAGE_HEADER_RE = re.compile(r"^\s*\d+\.\s+Passage\s+\d+\s*$")
_PASSAGE_TEXT_RE = re.compile(r"^\s+text:\s*(.*)$")


def parse_passages(payload_text):
    """Parse get_case_passages' structured-prose payload into a list of
    passage strings (identical behavior to the original in
    scripts/measure_anchoring.py -- see there for the format writeup).

        Returned N passages.

        1. Passage 1
           text: <passage text, one logical value, may wrap onto
           continuation lines with no 'text:' prefix>
        2. Passage 2
           text: ...
    """
    passages, current = [], None
    for line in payload_text.splitlines():
        if _PASSAGE_HEADER_RE.match(line):
            current = None
            continue
        m = _PASSAGE_TEXT_RE.match(line)
        if m:
            current = m.group(1)
            passages.append(current)
        elif current is not None and line.strip():
            passages[-1] = passages[-1] + " " + line.strip()
    return passages


# ------------------------------------------------------------- normalization

_QUOTES = {"“": '"', "”": '"', "‘": "'", "’": "'"}
_DASHES = {"–": "-", "—": "-"}

# Citation-divergence normalization (feasibility report Sec 4-5): the single
# largest source of exact/normalized-tier misses is Descrybe's passage
# extraction dropping the volume number immediately after "supra" (CourtListener
# "Green, supra, 10 Cal.3d 616" vs Descrybe's "Green, supra, Cal.3d 616") --
# strip that volume number from both sides so the pattern can't cost a tier.
_SUPRA_VOLUME_RE = re.compile(r"(supra,\s*)\d+\s+", re.I)

# Parallel-citation runs (e.g. "38 Cal.3d 454, 698 P.2d 116, 213 Cal. Rptr.
# 213") are where Descrybe's extraction has been observed to stitch or drop
# individual reporters (report Sec 4) -- collapse a comma-separated run of
# citation-shaped tokens down to just the first one so the run can't cost a
# match on either side. Heuristic, not a citation parser: "<digits> <reporter
# token> <digits>", reporter token allows letters/dots/digits (Cal.3d, P.2d,
# U.S., Cal. Rptr.).
_CITE_TOKEN = r"\d+\s+[A-Za-z][A-Za-z.]*\s*\d*[a-z]*\.?\s+\d+"
_PARALLEL_CITE_RUN_RE = re.compile(
    r"(" + _CITE_TOKEN + r")(?:,\s*" + _CITE_TOKEN + r")+", re.I
)


def normalize(text):
    for a, b in {**_QUOTES, **_DASHES}.items():
        text = text.replace(a, b)
    text = _SUPRA_VOLUME_RE.sub(r"\1", text)
    text = _PARALLEL_CITE_RUN_RE.sub(r"\1", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


# ------------------------------------------------------------------- fuzzy locate

def fuzzy_locate(passage_norm, text_norm, threshold=FUZZY_THRESHOLD,
                  step_divisor=4, top_k=15, max_windows=4000):
    """Sliding-window fuzzy locate: window size = len(passage_norm), stepped
    across text_norm. Cheap difflib.quick_ratio() ranks all windows first
    (a fast upper-bound), then the real .ratio() (actual SequenceMatcher
    edit-similarity) is computed only for the top_k candidates -- makes the
    O(n) windows x O(passage) ratio() cost tractable without approximating
    the reported best ratio.

    Returns (best_ratio, located: bool).
    """
    n = len(passage_norm)
    m = len(text_norm)
    if n == 0 or m < n:
        return 0.0, False
    step = max(10, n // step_divisor)
    if (m - n) // step + 1 > max_windows:
        step = max(step, (m - n) // max_windows)

    sm = difflib.SequenceMatcher(None, passage_norm, autojunk=False)
    candidates = []
    for start in range(0, m - n + 1, step):
        window = text_norm[start:start + n]
        sm.set_seq2(window)
        candidates.append((sm.quick_ratio(), start))
    # always check the final window too (range() may not land exactly on m-n)
    if (m - n) % step != 0:
        candidates.append((0.0, m - n))

    candidates.sort(reverse=True)
    best = 0.0
    for _, start in candidates[:top_k]:
        window = text_norm[start:start + n]
        r = difflib.SequenceMatcher(None, passage_norm, window, autojunk=False).ratio()
        best = max(best, r)
    return best, best >= threshold


# ------------------------------------------------------------- paragraph anchor

def anchor_passage(passage, paragraphs, threshold=FUZZY_THRESHOLD):
    """Locate `passage` (a Descrybe get_case_passages string) within
    `paragraphs`, a list of (paragraph_id, paragraph_text) pairs in document
    order (paragraph_text is plain text -- tag-stripped, unnormalized, in its
    original casing/punctuation).

    Tries exact substring, then normalized substring, then a per-paragraph
    fuzzy sliding-window locate (report Sec 5's recommended fallback chain,
    now anchored to paragraph granularity rather than the whole opinion --
    report Sec 5's "paragraph-granularity refinement").

    Returns {status, paragraph_id, ratio, char_start, char_end}. status is
    one of "exact"/"normalized"/"fuzzy"/"unanchorable". char_start/char_end
    are offsets into the ORIGINAL (unnormalized) paragraph text and are only
    populated for "exact" -- normalized/fuzzy hits anchor at the paragraph
    level only, per the report's offset-mapping caveat (Sec 5/6): turning a
    fuzzy match into a real character span requires a normalized-index-to-
    raw-index map that hasn't been built, so those tiers deliberately don't
    attempt it.
    """
    if not passage or not passage.strip() or not paragraphs:
        return {"status": "unanchorable", "paragraph_id": None, "ratio": None,
                "char_start": None, "char_end": None}

    for pid, ptext in paragraphs:
        idx = ptext.find(passage)
        if idx != -1:
            return {"status": "exact", "paragraph_id": pid, "ratio": 1.0,
                    "char_start": idx, "char_end": idx + len(passage)}

    passage_norm = normalize(passage)
    if passage_norm:
        for pid, ptext in paragraphs:
            if passage_norm in normalize(ptext):
                return {"status": "normalized", "paragraph_id": pid, "ratio": 1.0,
                        "char_start": None, "char_end": None}

    best_pid, best_ratio = None, 0.0
    for pid, ptext in paragraphs:
        ratio, _ = fuzzy_locate(passage_norm, normalize(ptext), threshold=threshold)
        if ratio > best_ratio:
            best_ratio, best_pid = ratio, pid

    if best_pid is not None and best_ratio >= threshold:
        return {"status": "fuzzy", "paragraph_id": best_pid, "ratio": best_ratio,
                "char_start": None, "char_end": None}

    return {"status": "unanchorable", "paragraph_id": None,
            "ratio": best_ratio if best_pid is not None else None,
            "char_start": None, "char_end": None}
