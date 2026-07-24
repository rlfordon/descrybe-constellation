"""CourtListener graph layer: clusters, backward edges (opinions_cited),
forward edges (cites: search). All calls cached; fields trimmed aggressively.
"""

import re

import requests

CL_BASE = "https://www.courtlistener.com/api/rest/v4"
_OPINION_URL_RE = re.compile(r"/opinions/(\d+)/?$")
_DOCKET_URL_RE = re.compile(r"/dockets/(\d+)/?$")


def opinion_id_from_url(url):
    m = _OPINION_URL_RE.search(str(url))
    return int(m.group(1)) if m else None


def docket_id_from_url(url):
    m = _DOCKET_URL_RE.search(str(url))
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

    def court_of_cluster(self, cluster_id):
        """Court name + id for a cluster, via its docket (cluster -> docket
        -> court; each hop a separate cached _get, like the other methods).
        Verified live: docket's "court" field is a URL, not a name -- one
        more hop to /courts/{id}/ resolves the readable name."""
        cluster = self._get(f"clusters/{cluster_id}/", fields="id,docket")
        did = docket_id_from_url(cluster.get("docket"))
        if did is None:
            return {"court": None, "court_id": None}
        docket = self._get(f"dockets/{did}/", fields="court,court_id")
        court_id = docket.get("court_id")
        court_name = None
        if court_id:
            court = self._get(f"courts/{court_id}/", fields="id,full_name")
            court_name = court.get("full_name")
        return {"court": court_name, "court_id": court_id}

    def match_clusters_by_text(self, cluster_ids, terms):
        """Cluster IDs (subset of cluster_ids) whose opinion text matches
        terms, via v4 search's fielded cluster_id query -- verified live that
        'q=(<terms>) AND cluster_id:(id1 OR id2 OR ...)' works. Chunked to
        ~40 ids per query (paged within a chunk if CL truncates); cached per
        (terms, chunk)."""
        ids = sorted(set(cluster_ids))
        matched = set()
        for i in range(0, len(ids), 40):
            chunk = ids[i:i + 40]
            key = f"cl:match:{terms}:{chunk}"

            def fetch(chunk=chunk):
                id_clause = " OR ".join(str(c) for c in chunk)
                found, url, params = set(), f"{CL_BASE}/search/", {
                    "q": f"({terms}) AND cluster_id:({id_clause})",
                    "type": "o",
                    "fields": "cluster_id",
                }
                pages = 0
                while url and pages < 5:
                    r = self._session.get(url, params=params, timeout=60)
                    r.raise_for_status()
                    data = r.json()
                    for row in data.get("results", []):
                        cid = row.get("cluster_id")
                        if cid is not None:
                            found.add(cid)
                    url, params, pages = data.get("next"), None, pages + 1
                return sorted(found)

            matched.update(self.cache.get_or(key, fetch))
        return matched

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
