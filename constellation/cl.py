"""CourtListener graph layer: clusters, backward edges (opinions_cited),
forward edges (cites: search). All calls cached; fields trimmed aggressively.
"""

import re

import requests

CL_BASE = "https://www.courtlistener.com/api/rest/v4"
_OPINION_URL_RE = re.compile(r"/opinions/(\d+)/?$")


def opinion_id_from_url(url):
    m = _OPINION_URL_RE.search(str(url))
    return int(m.group(1)) if m else None


class CourtListener:
    def __init__(self, token, cache):
        self.cache = cache
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Token {token}"

    def _get(self, path, **params):
        key = f"cl:{path}:{sorted(params.items())}"

        def fetch():
            r = self._session.get(f"{CL_BASE}/{path}", params=params, timeout=60)
            r.raise_for_status()
            return r.json()

        return self.cache.get_or(key, fetch)

    def cluster(self, cluster_id):
        return self._get(
            f"clusters/{cluster_id}/",
            fields="id,case_name,date_filed,citation_count,sub_opinions,precedential_status",
        )

    def opinion_ids(self, cluster_id):
        return [
            oid
            for oid in map(opinion_id_from_url, self.cluster(cluster_id).get("sub_opinions", []))
            if oid is not None
        ]

    def cluster_id_of_opinion(self, opinion_id):
        data = self._get(f"opinions/{opinion_id}/", fields="id,cluster_id")
        return data.get("cluster_id")

    def cited_opinions(self, opinion_id):
        """Backward edges: the opinion's table of authorities, as opinion IDs."""
        data = self._get(f"opinions/{opinion_id}/", fields="id,opinions_cited")
        return [
            oid
            for oid in map(opinion_id_from_url, data.get("opinions_cited", []))
            if oid is not None
        ]

    def citing_clusters(self, opinion_id, max_pages=3):
        """Forward edges: search rows for cases citing this opinion.

        Returns (rows, total_count, truncated). Rows carry caseName, dateFiled,
        cluster_id, court, citeCount, status. Cursor-paged; capped at max_pages
        (no silent truncation — the flag is returned).
        """
        key = f"cl:cites:{opinion_id}:pages{max_pages}"

        def fetch():
            rows, url, params = [], f"{CL_BASE}/search/", {
                "q": f"cites:({opinion_id})",
                "type": "o",
                "fields": "caseName,dateFiled,cluster_id,court,court_id,citeCount,status",
            }
            total, pages = None, 0
            while url and pages < max_pages:
                r = self._session.get(url, params=params, timeout=60)
                r.raise_for_status()
                data = r.json()
                total = data.get("count", total)
                rows.extend(data.get("results", []))
                url, params, pages = data.get("next"), None, pages + 1
            return {"rows": rows, "count": total, "truncated": total is not None and len(rows) < total}

        data = self.cache.get_or(key, fetch)
        return data["rows"], data["count"], data["truncated"]
