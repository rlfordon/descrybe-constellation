# Backlog

Observed issues and planned work, in rough priority order. Items here are
deliberately parked — resolve open design questions first, then batch.

## Timeline view (reported 2026-07-24, first hands-on use)

1. **DONE (2026-07-24, UX pass phase 2).** Axis doesn't track pan/zoom.
   Fixed: `renderTimelineAxis()` now re-renders on cytoscape
   `zoom`/`pan`/`resize` (rAF-throttled), mapping stored model-space tick/
   lane coordinates to rendered coordinates via `cy.zoom() * x + cy.pan().x`
   (same for lane y's). Tick years are now "nice" round steps (hand-rolled —
   see `static/app.js` `niceYearTicks`; vendoring d3-scale/d3-axis was
   evaluated and rejected as not self-contained, see phase-2 commit).
2. **DONE (2026-07-24, UX pass phase 2).** Zoom was purely magnifying — no
   semantic zoom. Fixed: node width/height/border-width/font-size are now
   divided by `cy.zoom()` (`zoomFactor` in `static/app.js`, forced via
   `cy.style().update()` on every zoom/pan/resize), applied to both force
   and timeline layouts and mirrored in the snapshot export's viewer
   (`constellation/web.py` `SNAPSHOT_TEMPLATE`). Zoom-tiered label density
   (true LOD, UX survey §7) remains out of scope for this pass and is not
   yet scheduled.

## Issue filter

- Works functionally as intended; UX is rough (placement, feedback, clearing,
  discoverability). Fold into the UX/UI pass below rather than patching.

## UX/UI pass (phases 1-2 done 2026-07-24; phase 3 not started)

Big coordinated pass rather than incremental patches: research phase first
(survey comparable graph/timeline research tools and visualization idioms;
subagent-driven), produce concrete mockups/recommendations, then implement.
Scope includes: left-pane flow (search → clusters → hops reads as a wall of
controls), filter affordances, case-card layout with 23k-char summaries,
legend/encoding legibility, empty states, and the header button sprawl
(dossier/trail/snapshot exports). Plan: `docs/ux-spec.md`; evidence:
`docs/research/2026-07-24-ux-survey.md`.

- [x] Phase 1 (structure & flow — filter bar, resizable panes, staged left
  pane, export dropdown, empty states) — implemented 2026-07-24.
- [x] Phase 2 (timeline & zoom correctness — axis tracks pan/zoom,
  counter-scaling zoom) — implemented 2026-07-24; see "Timeline view" above.
- [ ] Phase 3 (case reader: full-opinion reading view + passage anchoring) —
  not started. Feasibility (passage→opinion-text anchoring) measured in
  `docs/research/2026-07-24-case-reader-feasibility.md`; gate item 12 in
  `docs/ux-spec.md` (re-run the anchoring measurement on a second corpus)
  still needs doing before this phase is built.

Decided inputs (maintainer, 2026-07-24):
- The issue filter applies to the right-pane Leading/Case column as well as
  the graph — one filter state, every view respects it.
- The filter belongs with "review"-type controls (right side / analysis
  surface), not the "build"-type controls on the left.
- Columns become resizable. Hideable/collapsible: adopt only if the survey
  supports it.
- Case-reader feature (part UX, part feature): fetch the full opinion text,
  highlight the Descrybe "on this issue" passages within it, and make them
  jump-to-able — reading the case with its issue-relevant passages lit up.
  Feasibility (passage→opinion-text anchoring) under measurement.

## HTML research trail (explicitly wanted)

Rich HTML twin of the Markdown trail export: chronological session record
with the graph snapshot embedded inline, collapsible per-event detail, source
labels. Markdown variant stays (paste-into-notes use case).

## Earlier parked items

- Duplicate CourtListener clusters for parallel-reported cases (Dwyer, Segal)
  want a merge pass keyed on case name + date proximity.
- Forward citers cap at 60/opinion (3 pages); surfaced in notes, could be a
  user-facing "fetch more" per node.
- Composed forward filtering (`cites:(id) <terms>`) as a cheaper alternative
  to post-hoc filtering when a filter is already active before a forward hop.
- "Deep filter" upgrade: grade dimmed-vs-lit via Descrybe
  `get_case_passages(case_id, focus)` success/quality — better signal than
  full-text term matching, at one call per checked node.
