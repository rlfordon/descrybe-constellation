# descrybe-constellation

Explore legal issues and the citation network around them — and watch the leading and foundational cases emerge.

A local web app built on [Descrybe Legal Engine](https://github.com/descrybe-com/descrybe-legal-engine-python) (issue search, case summaries, treatment screening) and the [CourtListener API](https://www.courtlistener.com/help/api/) (the citation graph, both directions). Start from a plain-English issue, grow a case corpus by *issue hops* and *citation hops*, and rank cases by explainable structural signals — within-corpus citations and multi-issue membership — instead of a black-box relevance score.

**Status:** working prototype — core library, web app, and both exports are functional. See [`docs/design.md`](docs/design.md) and [`docs/spike-findings.md`](docs/spike-findings.md).

Not legal advice — a research exploration tool. Outputs carry source labels and screening-level caveats.

## Quickstart

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/dle login                              # per-user Descrybe OAuth
echo "COURTLISTENER_API_TOKEN=your-token" >> .env  # free CourtListener token
.venv/bin/python scripts/serve.py                # http://127.0.0.1:8737
```

If `data/vendor/cytoscape.min.js` is missing, the server prints a one-line `curl` command to fetch it (no CDN dependency at runtime — it's vendored once and served locally, then inlined into snapshot exports).

The app is a three-pane single-page UI: the **left pane** drives issue hops — seed and variant search terms, an overlap-threshold slider, toggleable search-cluster chips, and citation-hop controls (backward/forward, with a call-count hint); the **center pane** is an interactive Cytoscape graph of the growing corpus, colored by discovery origin and sized by within-corpus citations, with foundational cases marked by a purple border; the **right pane** shows a case card (Descrybe summary, treatment, on-demand focused passages, and a "Read case" action into a full-opinion reader with issue passages highlighted and jump-to navigation) and a ranked "Leading" tab. Every action is logged to a research trail. **Export trail** downloads a Markdown record of the session with per-claim `[Descrybe]` / `[CourtListener]` source labels; **Export snapshot** downloads a self-contained interactive HTML copy of the graph that opens from `file://` with no external requests.

## License

Apache-2.0. Access to the hosted Descrybe Legal Engine service and the CourtListener API is separate and subject to their respective terms.
