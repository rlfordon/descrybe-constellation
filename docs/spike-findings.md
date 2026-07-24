# Discovery spike findings

**Date:** 2026-07-24. Live calls against both APIs; raw payloads in `spike_output/` (gitignored). Seed: "implied warranty of habitability defense to eviction," California. Answers keyed to design.md §8.

## F1 — The ID namespaces are shared: the mapping layer collapses ★

Descrybe `case_id` = `"c"` + **CourtListener cluster ID**. Verified 8/8 on the seed issue search by prefix-strip → `GET clusters/{id}` → name comparison (`bridge_hit_rate.json`): Green `c1182285`↔1182285, Stoiber `c2134128`↔2134128, etc.

Design §3's citation-string mapping layer is unnecessary: the bridge is a prefix strip, plus one `clusters/{id}` fetch to resolve `sub_opinions` → opinion IDs for `cites:` queries and `opinions_cited`. Keep the `unmapped` flag as a cheap invariant check (assert name similarity on first fetch; flag mismatches), since this is undocumented coupling that could change.

## F2 — No related-issues payload exists on this surface (design §2 revised)

- `search_focus: "legal_issue"` vs. general search: **identical results** for the seed query (byte-diff is only share-URL token timestamps). Each case carries a per-case label ("Matches the likely issue: Implied Warranty of Habitability") — one label, no menu of related issues.
- Broad query ("landlord tenant disputes"): falls back to "Semantically matches the search concept" — semantic search, still no issue list.
- `analyze_legal_question` on a ready fact pattern: returns literally `"Ready for research."`

The related-issues walk the workflows repo alludes to ("If Descrybe returns related legal issues…") did not manifest for any query tried. **Issue hops must be synthesized**: generate search variants (narrower fact-specific, broader doctrine-level, opposing formulations), overlap-cluster the *searches* by result Jaccard, opt-out inclusion as designed. Multi-issue membership becomes multi-search membership. If Descrybe's issue graph surfaces later (their site may expose more than MCP), it slots back in unchanged.

## F3 — Payload format: structured prose, parseable, detail-capped at 8

MCP text blocks, not JSON. Stable labeled fields per case entry: numbered `Name, citations` line, `case_id:`, `court/date:`, `why relevant:`, `research value:` (e.g. "Leading authority — …strong anchor"), sometimes `treatment:` ("Later cases include some distinguishing or cautionary treatment…"), `snippet:`, share `url:`. Header says "Returned 15 matching cases" but the payload details **8** ("Showing 8 of 15") with no visible paging mechanism — per-search yield is 8 cases. The embedded `treatment:` and `research value:` fields are free screening signals worth harvesting into node metadata.

## F4 — Citation edges: CourtListener is the graph source, decisively

For *Green v. Superior Court* (opinion 1182285):

| Direction | Descrybe | CourtListener |
|---|---|---|
| Backward | n/a (no tool) | `opinions_cited`: **71** clean opinion URLs |
| Forward | `find_cases_that_cite`: **25** (name/citation/court/date, appears authority-ordered) | `cites:` search: **114**, rich fields (`citeCount`, `status`, court, dates), paged 20/cursor |

CL for both directions as designed; Descrybe citers acceptable only as a quick top-slice view.

## F5 — Summaries are headnote-grade

`get_case_summary` for Green: ~23k chars of dense doctrinal prose. `get_case_details`: compact (~2.8k). Case cards can be generous.

## Practical notes

- SDK wiring: `LegalEngine.from_token_store()` (bare `LegalEngine()` raises `AuthenticationRequired` even when `dle login` is connected).
- CL citation-lookup, clusters, opinions, and `cites:` search all worked first try with token auth; `fields=` trimming works as documented.
