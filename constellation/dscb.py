"""Descrybe content layer: MCP calls + parser for the structured-prose payloads.

Spike finding F3: tool results are text blocks with stable labeled fields per
numbered case entry, detail-capped at 8 cases per search.
"""

import re

FIELD_NAMES = ["case_id", "court/date", "why relevant", "research value",
               "treatment", "snippet", "url"]
_ENTRY_RE = re.compile(r"^\s*(\d+)\.\s+(.+)$")
_FIELD_RE = re.compile(
    r"^\s+(" + "|".join(re.escape(f) for f in FIELD_NAMES) + r"):\s*(.*)$"
)


def parse_entries(text):
    """Parse a Descrybe search/citers text payload into case-entry dicts."""
    entries, current, field = [], None, None
    for line in text.splitlines():
        m = _ENTRY_RE.match(line)
        if m:
            name_line = m.group(2).strip()
            name = name_line.split(",")[0].strip()
            current = {"name": name, "citation_line": name_line, "fields": {}}
            entries.append(current)
            field = None
            continue
        if current is None:
            continue
        f = _FIELD_RE.match(line)
        if f:
            field = f.group(1)
            current["fields"][field] = f.group(2).strip()
        elif field and line.strip():
            # continuation of a wrapped field value
            current["fields"][field] += " " + line.strip()

    for e in entries:
        fields = e.pop("fields")
        e["case_id"] = fields.get("case_id")
        court_date = fields.get("court/date", "")
        court, _, date = court_date.partition(";")
        e["court"] = court.strip() or None
        e["date"] = date.strip() or None
        e["why_relevant"] = fields.get("why relevant")
        e["research_value"] = fields.get("research value")
        e["treatment"] = fields.get("treatment")
        e["snippet"] = fields.get("snippet")
    return [e for e in entries if e.get("case_id")]


def parse_counts(text):
    """(claimed, shown) from 'Returned N matching cases' / 'Showing K of N'."""
    claimed = re.search(r"Returned (\d+) matching cases", text)
    shown = re.search(r"Showing (\d+) of (\d+)", text)
    n_claimed = int(claimed.group(1)) if claimed else None
    n_shown = int(shown.group(1)) if shown else None
    return n_claimed, n_shown


def issue_labels(entries):
    """Harvest 'Matches the likely issue: X' labels for search-variant hops."""
    labels = set()
    for e in entries:
        m = re.search(r"likely issue:\s*(.+)", e.get("why_relevant") or "")
        if m:
            labels.add(m.group(1).strip().rstrip("."))
    return sorted(labels)


class Descrybe:
    """Cached wrapper over the Descrybe Legal Engine MCP tools."""

    def __init__(self, cache, engine=None):
        self.cache = cache
        self._engine = engine

    def engine(self):
        if self._engine is None:
            from descrybe_legal_engine import LegalEngine
            self._engine = LegalEngine.from_token_store()
        return self._engine

    def _text(self, tool, args):
        key = f"dscb:{tool}:{sorted(args.items())}"

        def fetch():
            payload = self.engine().call_tool(tool, args)
            content = payload.get("result", {}).get("content") or []
            if not content or content[0].get("type") != "text":
                raise RuntimeError(f"unexpected {tool} payload shape: {payload}")
            return content[0]["text"]

        return self.cache.get_or(key, fetch)

    def search(self, term, jurisdiction=None, sort="authority"):
        args = {"term": term, "sort": sort}
        if jurisdiction:
            args["jurisdiction"] = jurisdiction
        text = self._text("search_cases_by_concept", args)
        return parse_entries(text)

    def citers(self, case_id):
        return parse_entries(self._text("find_cases_that_cite", {"case_id": case_id}))

    def summary(self, case_id):
        return self._text("get_case_summary", {"case_id": case_id})

    def details(self, case_id):
        return self._text("get_case_details", {"case_id": case_id})

    def status(self, case_id):
        return self._text("check_case_status", {"case_id": case_id})
