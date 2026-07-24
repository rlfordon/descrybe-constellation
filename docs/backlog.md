# Backlog

Observed issues and planned work, in rough priority order. Items here are
deliberately parked — resolve open design questions first, then batch.

## Timeline view (reported 2026-07-24, first hands-on use)

1. **Axis doesn't track pan/zoom.** The year-tick / lane-label overlay is a
   static div layer; panning or zooming the graph leaves it behind, so ticks
   stop lining up with node positions. Fix sketch: re-render the overlay on
   cytoscape `pan`/`zoom` events, mapping model x → rendered x via
   `cy.zoom() * x + cy.pan().x` (same for lane y's).
2. **Zoom is purely magnifying — no semantic zoom.** Node sizes are model
   coordinates, so zooming in makes everything bigger without improving
   separation. Fix sketch: on `zoom`, divide node width/height (and font
   size) by `cy.zoom()` so glyphs hold constant screen size while positions
   spread — that makes zoom actually resolve overlaps on the timeline.
   Consider the same for force layout.

## Issue filter

- Works functionally as intended; UX is rough (placement, feedback, clearing,
  discoverability). Fold into the UX/UI pass below rather than patching.

## UX/UI pass (in progress 2026-07-24 — research phase running)

Big coordinated pass rather than incremental patches: research phase first
(survey comparable graph/timeline research tools and visualization idioms;
subagent-driven), produce concrete mockups/recommendations, then implement.
Scope includes: left-pane flow (search → clusters → hops reads as a wall of
controls), filter affordances, case-card layout with 23k-char summaries,
legend/encoding legibility, empty states, and the header button sprawl
(dossier/trail/snapshot exports).

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
