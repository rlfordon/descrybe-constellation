# descrybe-constellation — design

**Status:** design converged, pre-implementation. Next step: discovery spike (§8).
**Date:** 2026-07-24

## 1. What it is

A local web app for exploring legal issues and the citation network around them. You start from a plain-English legal issue, grow a corpus of cases along two axes — *issue hops* and *citation hops* — and watch the leading and foundational cases emerge from the structure of the network rather than from a black-box relevance rank.

Built on two public data layers:

- **[Descrybe Legal Engine](https://github.com/descrybe-com/descrybe-legal-engine-python)** — the *content layer*: issue-indexed case search, related issues, precomputed case summaries, issue-focused passages, treatment screening.
- **[CourtListener](https://www.courtlistener.com/help/api/)** — the *graph layer*: the citation network in both directions (an opinion's `opinions_cited` is its table of authorities; the `cites:` search query finds later citers).

Not legal advice; a research exploration tool. Outputs carry per-claim source labels and screening-level treatment caveats (see §7).

## 2. Corpus building — two hop axes, independently controlled

**Hop 0:** case results of the seed issue (Descrybe `search_cases_by_concept`, `search_focus: "legal_issue"`).

**Issue hops.** Related issues returned by the legal-issue search are frequently near-duplicates. They are deduped into *clusters* by result overlap: two issues whose top-k case results have high Jaccard similarity are treated as one cluster (tool-native similarity — no embeddings). Cluster inclusion is **opt-out**: clusters above an overlap threshold with the seed's results are included automatically; an "included issues" chip row makes pruning one click, with the graph updating live. The threshold is a user-facing slider (real-world overlap distributions unknown until the spike, §8). Including a cluster unions its case results into the corpus.

**Citation hops.** The citation network expands from corpus cases via CourtListener, in both directions:

- **Backward (foundations):** the opinion's `opinions_cited` — its table of authorities.
- **Forward (later treatment):** `cites:<opinion-id>` search — later cases citing it. Opinion IDs, not cluster IDs.

Each axis has its own hop-depth control. Expansion is always an explicit user action with a "this will make ~N calls" preview; the app never auto-crawls.

## 3. ID-mapping layer (the one novel component)

Descrybe and CourtListener use disjoint ID namespaces (`c1514149` vs. opinion/cluster IDs). Mapping goes through the reporter citation: Descrybe case details → citation string → CourtListener citation-lookup → opinion ID (and the reverse for citer-discovered cases entering the corpus, via Descrybe `find_case_from_reference`). Mappings are cached permanently.

**Failure mode is explicit:** a case that won't map cleanly stays in the graph as an edge-light node flagged `unmapped` — it never silently vanishes. Unmapped rates are surfaced in the UI; cross-corpus coverage is the load-bearing assumption of this design and gets measured, not presumed.

## 4. Graph model and UI

Three panes:

1. **Issue pane** — seed search, included-cluster chips, overlap-threshold slider.
2. **Case pane** — headnote-style cards: Descrybe summary up front, issue-focused passage (`get_case_passages`) on demand; full opinions are never fetched for browsing.
3. **Graph pane** — interactive directed graph (Cytoscape.js). Edge types rendered distinctly: backward = foundations, forward = later treatment (with both, the graph reads as a doctrine timeline). Nodes colored by court level, sized by within-corpus in-degree. Optional timeline layout. Click a node to expand either direction.

## 5. Leading and foundational cases

Ranking uses only explainable signals — no composite score, no vendor authority rank:

- **within-corpus citations** (in-degree over the induced subgraph),
- **multi-issue membership** (how many included issues' result sets contain the case),
- court level, date.

**Foundational badge:** high backward in-degree + decision date well before the corpus median + (typically) absent from issue search results — the anchor case issue search misses but everything cites.

**Screening badge:** Descrybe `check_case_status` on leading/foundational cases, always framed as a screening signal, not a citator conclusion.

## 6. Persistence and credentials

- **SQLite cache** keyed by Descrybe `case_id` / issue / opinion ID: every API result and ID mapping is paid for once; sessions reopen without re-spending calls.
- **Credentials:** users bring their own — `dle login` (per-user OAuth, per Descrybe's access model) and a free CourtListener API token. Nothing shared, nothing committed; `.gitignore` covers the cache and any env files.

## 7. Outputs

- **Research-trail export:** the exploration path (issues included, cases visited, expansions run) as Markdown with per-claim source labels — `[Descrybe]`, `[CourtListener]`, `[Model reasoning]`, `[Needs verification]` — and a research-current-through timestamp.
- **Static snapshot export:** a self-contained interactive HTML file of the current graph, viewable without any credentials. Canned snapshots in the README serve as live demos.

## 8. Discovery spike (build step 1)

Real calls before any app code, to pin down:

1. Shape of the related-issues payload from `search_focus: "legal_issue"` (and current issue-duplication behavior).
2. What `find_cases_that_cite` returns (metadata vs. bare IDs) — retained as a possible forward-edge cross-check even though CourtListener is the primary graph source.
3. CourtListener citation-lookup hit-rate on a real Descrybe result set (the §3 coverage measurement).
4. `opinions_cited` completeness/format on the mapped opinions; `cites:` result counts and paging.
5. Result-set sizes per issue (drives Jaccard k and threshold defaults).

## 9. Build order

1. Discovery spike (`scripts/spike.py`), findings recorded in `docs/spike-findings.md`.
2. Cache + ID-mapping layer, tested against spike fixtures.
3. Corpus engine (hop logic, clustering, ranking) — pure functions over the cache, UI-independent.
4. Web app (FastAPI + Cytoscape.js) over the corpus engine.
5. Exports (trail Markdown, static snapshot).

## 10. License

Apache-2.0. The hosted services remain subject to their own terms (Descrybe ToS; CourtListener API terms).
