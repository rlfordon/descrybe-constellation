# Case-reader anchoring feasibility

**Date:** 2026-07-24. Measured against the live APIs (cached; every call paid for once — `data/cache.sqlite`, 737 entries after this run). Test set: the 8 search-origin cases for seed "implied warranty of habitability defense to eviction," jurisdiction California — the same `dscb.search()` call `scripts/build_corpus.py` / the app's `/api/search` make. Script: [`scripts/measure_anchoring.py`](../../scripts/measure_anchoring.py), runnable on any other corpus by editing `SEED`/`JURISDICTION` at the top (all calls cached, reruns cost nothing).

**Question:** can each Descrybe `get_case_passages` passage be located inside the corresponding CourtListener opinion text, given the two vendors' independent text pipelines?

## Headline numbers

| Tier | Passages (of 21) | Cumulative % |
|---|---|---|
| Exact substring | 3 | 14.3% |
| Normalized substring (or better) | 5 | 23.8% |
| Fuzzy-located, ratio ≥ 0.85 (or better) | 19 | 90.5% |
| **Unanchorable** (best fuzzy ratio < 0.85) | 2 | 9.5% |

**Go**, with the fuzzy tier load-bearing and a mandatory honest-failure path for the ~10% tail. See §6 for caveats.

## 1. `get_case_passages` payload format

Never parsed before this repo (design.md names the tool; the discovery spike never exercised it). It is the same structured-prose family as `search_cases_by_concept` (spike F3) but single-field: an MCP text block, numbered entries, one labeled field per entry, no JSON.

```
Returned 3 passages.

1. Passage 1
   text: <passage text — one continuous string>
2. Passage 2
   text: <passage text>
3. Passage 3
   text: <passage text>
```

Observed across all 8 cases: each passage's `text:` value stays on a single line — no wrapping onto continuation lines was seen in this test set, though `scripts/measure_anchoring.py`'s `parse_passages()` still folds unlabeled continuation lines into the current passage defensively, on the same pattern as `dscb.parse_entries`'s field continuation handling, since the payload gives no format guarantee against it. Passage count per case ranged 1–3 (21 passages total across 8 cases; no case returned 0). Passages are plain text: straight or curly quotes as they appear in the source opinion, no HTML/markdown, no citation markup — but see §6 for cases where Descrybe's own extraction visibly mangles an embedded citation (dropped closing parens, dropped volume numbers).

## 2. CourtListener opinion text-field availability

Per-cluster: `cl.opinion_ids(cluster_id)` (from `sub_opinions`) can return one opinion (single-opinion cluster) or several (majority + concurrence/dissent + a "combined" entry covering all of them). All 15 opinion rows across the 8 cases were fetched with `fields=id,type,plain_text,html,html_with_citations,html_lawbox,xml_harvard`.

| Field | Non-empty rows | Coverage |
|---|---|---|
| `html_with_citations` | 15 / 15 | **100%** |
| `xml_harvard` | 11 / 15 | 73% — present on standalone/split sub-opinions, empty on the "combined" row when a cluster has split opinions |
| `html_lawbox` | 8 / 15 | 53% — inverse pattern: present on standalone/combined rows, empty on split sub-opinion parts |
| `plain_text` | 1 / 15 | 7% — populated for exactly one case (Erlach, `c2677838`) |
| `html` | 0 / 15 | 0% — never populated in this set |

`html_with_citations` is the only field available on every opinion row, so it's the field used for all anchoring measurement below (`PRIMARY_FIELD` in the script). Full per-opinion sizes are in the script's stdout table; e.g. Green v. Superior Court (`c1182285`): `html_with_citations` 121,602 chars, `html_lawbox` 70,616, `xml_harvard` 80,729, `plain_text`/`html` empty.

## 3. Anchoring-rate table

Per case, against the concatenation of that case's opinion(s) `html_with_citations`, HTML tags stripped to spaces and entities unescaped (no whitespace/quote normalization at this stage — see §5 for the pipeline). Percentages are cumulative (a passage counted at "normalized" also counts toward "fuzzy", etc.).

| Case | Passages | Exact % | Normalized % | Fuzzy-located % | Unanchorable |
|---|---|---|---|---|---|
| Green v. Superior Court (`c1182285`) | 3 | 0.0% | 33.3% | 100.0% | 0 |
| Stoiber v. Honeychuck (`c2134128`) | 1 | 0.0% | 0.0% | 100.0% | 0 |
| Peterson v. Superior Court (`c1360581`) | 3 | 0.0% | 0.0% | 66.7% | 1 |
| Becker v. IRM Corp. (`c1172788`) | 2 | 0.0% | 0.0% | 100.0% | 0 |
| Hinson v. Delis (`c2105369`) | 3 | 33.3% | 33.3% | 100.0% | 0 |
| Erlach v. Sierra Asset Servicing (`c2677838`) | 3 | 33.3% | 66.7% | 100.0% | 0 |
| Penner v. Falk (`c2116613`) | 3 | 33.3% | 33.3% | 100.0% | 0 |
| Fairchild v. Park (`c2256171`) | 3 | 0.0% | 0.0% | 66.7% | 1 |
| **Total** | **21** | **14.3%** | **23.8%** | **90.5%** | **2 (9.5%)** |

## 4. Why exact/normalized undershoot, and what the fuzzy tier is actually fixing

Inspecting the two unanchorable passages and a sample of fuzzy-only matches shows a consistent, non-random cause: **embedded pinpoint citations and italicized case names diverge in formatting between the two vendors**, not OCR noise or arbitrary whitespace.

- **Peterson v. Superior Court, passage 2** (best fuzzy ratio 0.814, below threshold). The passage's opening ~85% is a verbatim quote and matches CL cleanly; it fails because it tails into a law-review citation that CL renders as `…Premises—Becker` (em dash, then an italicized case name split across `<em>` tags: `Becker`, `v.`, `IRM Corp.,`) while Descrybe's extraction renders the same citation as `…Premises. Becker v. IRM Corp. 38 Cal.3d 454, 698 P.2d 116, 213 Cal. Rptr. 213 (1985. supra,` — note the mangled `(1985. supra,` where Descrybe's own pipeline appears to have swallowed the closing paren. This is a **Descrybe-side extraction artifact** on an embedded citation, not a CourtListener text-quality problem.
- **Fairchild v. Park, passage 1** (best fuzzy ratio 0.770, below threshold). Matches CL's text almost verbatim except that every pincite loses its volume number: CL has `Green, supra, 10 Cal.3d 616` and `Green, supra, 10 Cal.3d at p. 631`; Descrybe's passage has `Green, supra, Cal.3d 616` and `Green, supra, Cal.3d at p. 631` (no `10`). This "missing volume number after `supra`" pattern recurs across several *other* passages too (Peterson passage 3, Becker passage 1, Fairchild passages 2–3) — those still clear the fuzzy threshold because the passage is otherwise long and clean, but it's the single largest source of divergence found in this test set and looks systematic to Descrybe's passage pipeline rather than incidental.
- The normalized tier (quote/dash unification + whitespace collapse) only recovers 2 of 21 passages beyond exact match — most divergence is not whitespace/quote-style, it's the citation-text content itself, which whitespace normalization can't fix. That's why the fuzzy tier is load-bearing (66.7 percentage points of the total 90.5%), not a rare fallback.

## 5. Recommended anchoring strategy

**Normalization pipeline** (as measured): strip HTML tags to single spaces (never delete — avoids concatenating words across tag boundaries) → unescape HTML entities → unify curly quotes/dashes to ASCII → collapse all whitespace runs to one space → lowercase.

**Fallback chain**, per passage, cached forever once computed:

1. **Exact substring** in the tag-stripped (unnormalized) text.
2. **Normalized substring** — catches whitespace/quote/case differences only.
3. **Fuzzy sliding-window locate** (`difflib.SequenceMatcher`, window = passage length, stepped, `quick_ratio()` pre-filter then real `ratio()` on the top candidates — see `fuzzy_locate()` in the script for the two-pass cost-reduction, needed because a naive full-window `ratio()` sweep over a ~100–200K-char opinion is too slow to run per passage). Threshold 0.85, chosen because at 0.85 the two false-negative cases (0.814, 0.770) separate cleanly from the 19 true positives (all ≥ 0.867) — there's no borderline cluster near the cutoff in this sample, but that should be re-checked as the corpus grows.
4. **Unanchorable**: never dropped. Render the passage in the case card as today, but flag it in the reader view — per the app's existing convention (design.md §7) — as `[Needs verification]`: *"This passage could not be automatically located in the CourtListener opinion text; shown as-is, not jump-linked."* No auto-jump, no silent omission.

**Paragraph-granularity refinement (not yet measured, recommended next step):** `html_with_citations` carries `<p id="…">` paragraph tags (see §7) with apparently stable pagination-derived ids (e.g. `b619-8`, `A4e`). Rather than sliding a window over the whole opinion, splitting on `<p>` boundaries and fuzzy-matching each passage against individual paragraphs would (a) likely raise the fuzzy-tier success rate, since paragraphs are shorter and more self-contained than an arbitrary stepped window, and (b) give the anchor target for free — highlight/scroll to the matched `<p id>` rather than needing exact character offsets. This is a natural next increment on top of what's measured here, not implemented or tested in this pass.

**Offset mapping caveat:** the measurement above answers *locatable or not*, using a normalized copy of the text for tiers 2–3. Turning a fuzzy match into an actual highlight/scroll target in the reader requires mapping the matched span back to a real character offset (or `<p id>`) in the original `html_with_citations` markup — a normalized-index-to-raw-index map, or (per the refinement above) paragraph-level matching that sidesteps the offset-mapping problem entirely. Neither is built yet; flagging it as implementation scope, not a measured unknown.

## 6. Caveats

- **Small test set.** 8 cases, 21 passages, one doctrine, one jurisdiction, all pre-2000s except Fairchild. The systematic "missing volume number after `supra`" and citation-mangling patterns found here are plausible as general Descrybe-pipeline behavior but are only directly evidenced on a handful of passages — worth confirming on a second corpus before hard-coding assumptions into the anchoring pipeline (the script is built to make that rerun free).
- **0.85 threshold has no borderline cluster in this sample** (nearest miss above the cutoff: 0.867; nearest hit below: 0.814) — reasonable for now, but revisit once more corpora are run since a threshold picked on 21 passages could still be in the wrong place for other doctrines' citation density.
- **Multi-opinion clusters** (3 of 8 cases here: Stoiber, Becker, Fairchild) were handled by concatenating every sub-opinion's `html_with_citations`, which duplicates content between the "combined" row and its split parts (both were fetched and concatenated) — harmless for a locate-or-not substring/fuzzy test, but the real reader will need to pick one canonical opinion (or render sub-opinions separately) rather than concatenate everything.
- **`plain_text` is not viable as a primary field** — 1 of 15 opinion rows had it. `html_with_citations` is the only dependable field in this API; if it were ever unavailable for a given opinion, there's no clean same-shape fallback among the fields checked (`xml_harvard`/`html_lawbox` have complementary but non-overlapping coverage on split-opinion clusters — see §2 — so a real fallback chain should prefer `html_with_citations` → `xml_harvard` → `html_lawbox` in that order per opinion, not case-wide).
- **Runtime cost**: the fuzzy tier (`difflib.SequenceMatcher`) is the expensive step. Full run (21 passages, 8 cases, fully cached network calls) takes ~25–28s wall time, almost entirely `quick_ratio`/`ratio` computation. Fine as a one-time, cache-forever computation triggered on reader open (§7), not fine if it were ever run synchronously per page-view.

## 7. Recommended data flow

- **CL text field:** `html_with_citations` only (only universally-available field; also the one carrying paragraph structure — see below). Fetch via `opinions/{id}/` with `fields=id,type,html_with_citations` (trim further if paragraph ids/citation spans aren't needed beyond anchoring). For multi-opinion clusters, resolve which opinion(s) to render as a product decision (§6) before wiring this in — don't default to "concatenate everything," that was a measurement-only shortcut.
- **Passages:** `get_case_passages` with `focus` = the current issue string, same call the dossier already makes, parsed with `parse_passages()` (or a promoted version of it in `dscb.py`).
- **When to fetch:** on reader open, not on case-card render (matches design.md §4 — "full opinions are never fetched for browsing"). Both the opinion text and the passages are immutable published documents, so cache forever, same as every other call in this app (`constellation/cache.py`'s `get_or`, no TTL).
- **Cache keys:** opinion text reuses the existing `cl:{path}:{params}` key shape (`cl._get`'s convention) — no new key scheme needed. Passages reuse `dscb:{tool}:{args}` (`dscb._text`'s convention). The one new cache-worthy artifact is the **anchor computation itself** (tier, matched offset/paragraph id, fuzzy ratio) — recommend a new key namespace, e.g. `anchor:{case_id}:{focus}:{passage_index}`, storing the resolved tier + location so the ~25s fuzzy sweep runs once per (case, focus, passage) ever, not once per reader-open.
- **Never silently drop:** every passage renders in the reader regardless of anchoring outcome; only the jump-link/highlight behavior differs by tier (exact/normalized/fuzzy: highlight + jump-to; unanchorable: passage text shown with the `[Needs verification]` marker from design.md §7's source-label convention, no jump-to).

## 8. Go/no-go

**Go**, for the "highlight + jump-to inside the full opinion" case-reader feature described in the design, with these conditions carried into implementation:

1. The fuzzy-locate tier is not optional — it recovers 66.7 of the 90.5 total anchored percentage points. Ship it as a first-class part of the pipeline, not a rare fallback.
2. Build the honest-failure UI (`[Needs verification]`, no jump-link) for the unanchorable tail from day one — at ~9.5% on this sample it's infrequent but not negligible, and design.md's own convention already calls for exactly this pattern.
3. Re-run `scripts/measure_anchoring.py` against at least one more corpus (different doctrine/jurisdiction/date range) before finalizing the 0.85 threshold and the field-preference fallback order — this run validates the *approach*, not the specific constants, on a sample of 21 passages.
4. Treat exact-character-offset highlighting as a follow-on increment; paragraph-level anchoring via `html_with_citations`'s `<p id="…">` structure (confirmed present, with citation `<span data-id>` markup as a bonus for future forward-link rendering) is very likely both easier to implement and more accurate than raw character offsets, and should be prototyped before committing to an offset-mapping approach.

## Second-corpus validation (gate item 12, run 2026-07-24)

Seed "qualified immunity clearly established law", jurisdiction Federal — 8
search-origin cases, 24 passages, measured with the same script (results in
full in the run log; headline numbers):

- exact 0/24 (0.0%), normalized 0/24 (0.0%) — federal-reporter parallel
  citations and curly/straight quote divergence eliminate the cheap tiers
  entirely on this corpus.
- fuzzy >= 0.85: 21/24 (87.5%) anchored; unanchorable 3/24 (12.5%).
- Field availability again favors `html_with_citations` (8/8 opinions,
  several with NO plain_text or html at all).

**Gate verdict: threshold 0.85 validated** (87.5% here vs 90.5% on the
habitability corpus; ~89% combined across 45 passages). Design consequence:
the fuzzy tier is the PRIMARY anchoring mechanism, not a fallback — exact/
normalized are cheap first passes only. The unanchorable tail is real and
includes passages whose best window ratio is far below threshold (0.345,
0.607) — consistent with Descrybe passage extraction sometimes stitching
context rather than quoting verbatim — so the [Needs verification] UI is
mandatory, not decorative.
