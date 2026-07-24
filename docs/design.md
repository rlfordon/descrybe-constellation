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

**Issue hops** *(revised per spike F2 — no related-issues payload exists on the MCP surface)*. Issue hops are synthesized as **search-variant hops**: from the seed issue, generate variant formulations (narrower fact-specific, broader doctrine-level, opposing framings — optionally harvesting the per-case "likely issue" labels search results carry), run each as its own search, and dedupe the *searches* into clusters by result overlap: two searches whose top-k case results have high Jaccard similarity are treated as one cluster (tool-native similarity — no embeddings). Cluster inclusion is **opt-out**: clusters above an overlap threshold with the seed's results are included automatically; an "included searches" chip row makes pruning one click, with the graph updating live. The threshold is a user-facing slider. Including a cluster unions its case results into the corpus (per-search yield is 8 detailed cases — spike F3 — so variant breadth matters). If Descrybe later exposes its issue graph over MCP, vendor issues slot into this same clustering unchanged.

**Citation hops.** The citation network expands from corpus cases via CourtListener, in both directions:

- **Backward (foundations):** the opinion's `opinions_cited` — its table of authorities.
- **Forward (later treatment):** `cites:<opinion-id>` search — later cases citing it. Opinion IDs, not cluster IDs.

Each axis has its own hop-depth control. Expansion is always an explicit user action with a "this will make ~N calls" preview; the app never auto-crawls.

## 3. ID bridge *(collapsed per spike F1)*

The namespaces turn out to be shared: Descrybe `case_id` = `"c"` + CourtListener **cluster** ID (verified 8/8 on the spike seed). The bridge is a prefix strip plus one `clusters/{id}` fetch to resolve `sub_opinions` → opinion IDs for citation queries. Because this coupling is undocumented, every first fetch asserts name similarity between the two records; a mismatch flags the node `unmapped` (edge-light, never silently dropped) and surfaces in the UI. Mappings and assertions are cached permanently.

## 4. Graph model and UI

Three panes:

1. **Issue pane** — seed search, included-cluster chips, overlap-threshold slider.
2. **Case pane** — headnote-style cards: Descrybe summary up front, issue-focused passage (`get_case_passages`) on demand; full opinions are never fetched for browsing.
3. **Graph pane** — interactive directed graph (Cytoscape.js). Edge types rendered distinctly: backward = foundations, forward = later treatment (with both, the graph reads as a doctrine timeline). Nodes colored by court level, sized by within-corpus in-degree. Optional timeline layout. Click a node to expand either direction.

### Amendments (2026-07-24, post-review)

- **Timeline layout.** A client-side preset alternative to the force (cose) layout, toggled per-session: x = decision year scaled across the pane width (undated nodes to a left gutter), y = four lanes (high/appellate/trial/unknown) with jitter to reduce overlap. Year ticks and lane labels render as an absolutely-positioned div layer over the graph pane.
- **Encoding.** Node color now encodes court level (`corpus.court_level`, a keyword heuristic parallel to `court_weight`, backfilled via `cl.court_of_cluster`); origin moved to shape (ellipse/diamond/triangle for search/backward/forward); size scales with `log(1 + citation_count)`, normalized [14, 64]. Foundational purple border unchanged. A small legend is always visible in the graph pane.
- **Issue filter.** A batched post-hoc text filter (`cl.match_clusters_by_text`, fielded `cluster_id:` search, chunked ~40 ids) rather than composed `cites:` queries at each forward hop -- simpler, and the fielded query was verified live. Search-origin nodes are assumed matching (they already matched this issue by construction); only backward/forward nodes get a real text check. Non-matching nodes and their edges dim to 0.12 opacity; nothing is ever deleted.

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

## 8. Discovery spike — **done 2026-07-24**

Findings in [`spike-findings.md`](spike-findings.md). Headlines: shared ID namespaces (F1, collapses §3); no related-issues payload on the MCP surface (F2, revises §2); structured-prose payloads detail-capped at 8 cases with embedded treatment/research-value fields (F3); CourtListener decisively the graph source — 71 backward / 114 forward edges for the anchor case vs. 25 forward from Descrybe (F4); summaries are headnote-grade at ~23k chars (F5).

## 9. Build order

1. ~~Discovery spike~~ — done; `scripts/spike.py`, findings in `docs/spike-findings.md`.
2. Cache + ID bridge (prefix strip + name-assertion), tested against spike fixtures.
3. Corpus engine (hop logic, clustering, ranking) — pure functions over the cache, UI-independent.
4. Web app (FastAPI + Cytoscape.js) over the corpus engine.
5. Exports (trail Markdown, static snapshot).

## 10. License

Apache-2.0. The hosted services remain subject to their own terms (Descrybe ToS; CourtListener API terms).
