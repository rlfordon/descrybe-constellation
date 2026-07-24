# descrybe-constellation

Explore legal issues and the citation network around them — and watch the leading and foundational cases emerge.

A local web app built on [Descrybe Legal Engine](https://github.com/descrybe-com/descrybe-legal-engine-python) (issue search, case summaries, treatment screening) and the [CourtListener API](https://www.courtlistener.com/help/api/) (the citation graph, both directions). Start from a plain-English issue, grow a case corpus by *issue hops* and *citation hops*, and rank cases by explainable structural signals — within-corpus citations and multi-issue membership — instead of a black-box relevance score.

**Status:** design phase. See [`docs/design.md`](docs/design.md). Next step is a discovery spike against the live APIs.

Not legal advice — a research exploration tool. Outputs carry source labels and screening-level caveats.

## License

Apache-2.0. Access to the hosted Descrybe Legal Engine service and the CourtListener API is separate and subject to their respective terms.
