# UX/UI pass — implementation spec

**Date:** 2026-07-24. Synthesis of `research/2026-07-24-ux-survey.md` (pattern
survey) and `research/2026-07-24-case-reader-feasibility.md` (measured
anchoring rates), constrained by the maintainer's decided inputs in
`backlog.md`. Three phases, independently shippable, in order.

## Phase 1 — structure & flow (CSS/JS only, no backend)

1. **Filter moves to the review surface.** A persistent filter bar sits above
   the right-pane tabs: input (prefilled with seed), Filter/Clear, and an
   always-visible **"N of M match"** count. One filter state, every view
   respects it: the graph keeps its 0.12-opacity dimming; the Leading table
   and foundational list dim non-matching rows the same way (never hide) and
   show the count badge so a filtered list can't read as complete. Left pane
   loses its filter controls entirely (build vs. review separation).
2. **Resizable panes.** Vanilla drag handles between the three panes;
   min-widths (left 220px, right 280px); sizes persisted to localStorage;
   `cy.resize()` fires after any drag affecting the center pane (Cytoscape
   does not observe flex resizes). **No hideable panes**: research found
   collapse precedent only for navigation sidebars, not panels holding live
   editable state; right-pane collapse rejected, left-pane collapse parked.
3. **Left-pane staged flow.** Progressive disclosure without hiding
   revisable state: three labeled stages (1 Search, 2 Clusters, 3 Hops).
   Stages 2–3 render collapsed-but-visible headers until their inputs exist,
   then expand; earlier stages stay open and editable. Chip row and threshold
   slider stay together in stage 2.
4. **Header consolidation.** One **Export ▾** menu (Trail / Snapshot /
   Dossier) plus a standalone **Dossier** view button; title and the
   research-support note stay.
5. **Empty states.** Each pane gets a one-paragraph first-run state: left
   explains the seed→variants idea; center explains what the graph will show
   (with the legend visible); right says "click a node or build a corpus."

## Phase 2 — timeline & zoom correctness

6. **Axis tracks pan/zoom.** Re-render tick/lane overlay on Cytoscape
   `pan`/`zoom`/`resize` events, mapping model→rendered coords
   (`cy.zoom() * x + cy.pan().x`). Vendor `d3-scale` + `d3-axis` (two small
   static files, same vendoring pattern as cytoscape) rather than hand-rolled
   tick math.
7. **Counter-scaling zoom.** On `zoom`, divide node width/height/font by
   `cy.zoom()` so glyph screen size stays constant while positions spread —
   zooming then genuinely resolves overlaps. Applies in both layouts.
   Zoom-tiered label density (true LOD) stays in backlog as a later layer.

## Phase 3 — case reader (feature; backend + frontend)

8. **Reading view** replaces the Case tab content on "Read case" (card
   header keeps a back affordance). Text source: CourtListener
   `html_with_citations` — the only universally available field (15/15 in
   measurement) and it carries `<p id>` paragraph anchors and citation spans.
   Sanitized server-side (strip scripts/styles/attrs beyond the anchor ids),
   cached forever.
9. **Passage anchoring** (per measured rates: exact 14.3%, +normalized
   23.8%, +fuzzy ≥0.85 → 90.5%): pipeline is exact → normalized (whitespace/
   quotes/dashes, case-insensitive) → sliding-window SequenceMatcher with
   0.85 threshold — the fuzzy tier is load-bearing, not a fallback. Anchor to
   paragraph level. Highlights + prev/next passage navigation + scrollbar
   tick indicators (find-in-page pattern). Root cause of misses is Descrybe's
   pinpoint-citation rendering divergence, so normalization should also strip
   volume-number patterns around "supra" before fuzzy is attempted.
10. **Honest failure from day one:** unanchorable passages (~9.5%) render in
    a "[Needs verification] — passage returned by Descrybe but not located
    in the CourtListener text" block above the opinion, showing the passage
    itself. Never silently dropped.
11. **Open official PDF** button in the reader via Descrybe `get_case_pdf`
    (live app only; exports remain self-contained and link-free).
12. **Gate before merge:** re-run `scripts/measure_anchoring.py` on a second
    corpus (different doctrine + jurisdiction) to validate the 0.85
    threshold beyond the initial 21-passage sample; record results in the
    feasibility report.

## Out of scope for this pass

Hideable panes (parked), LOD label density (backlog), HTML trail export
(explicitly queued separately), duplicate-cluster merge, "fetch more citers".
