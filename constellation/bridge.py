"""Descrybe <-> CourtListener ID bridge.

Spike finding F1: Descrybe case_id = "c" + CourtListener cluster ID (8/8 on
the spike seed). The coupling is undocumented, so every crossing asserts name
similarity between the two records; failures are flagged, never dropped.
"""

import re

CASE_ID_RE = re.compile(r"^c(\d+)$")


def to_cluster_id(case_id):
    m = CASE_ID_RE.match(case_id.strip())
    if not m:
        raise ValueError(f"not a Descrybe case_id: {case_id!r}")
    return int(m.group(1))


def to_case_id(cluster_id):
    return f"c{int(cluster_id)}"


def _norm(name):
    name = re.sub(r"[^a-z0-9 ]", "", name.lower())
    return re.sub(r"\s+", " ", name).strip()


def names_match(descrybe_name, cl_name):
    """Loose containment check between the two vendors' case names."""
    a, b = _norm(descrybe_name), _norm(cl_name)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    # fall back to first-party comparison ("green v superior court" -> "green")
    return a.split(" v ")[0] == b.split(" v ")[0]
