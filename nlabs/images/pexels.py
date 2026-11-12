# images/pexels.py — Pexels API for generic B-roll photos (buildings, chips, courtrooms…).
# Optional key in ~/.config/umf/pexels.env. Pexels license: free to use, credit appreciated.
# Never used for photos claimed to show a real person.
def search(query, key, n=10, client=None):
    from ..util import http_client
    c = client or http_client()
    r = c.get("https://api.pexels.com/v1/search", params={"query": query, "per_page": n},
              headers={"Authorization": key})
    r.raise_for_status()
    return [{"source": "pexels", "url": p["src"]["large2x"], "page": p["url"], "title": p.get("alt", ""),
             "license": "Pexels License", "author": p.get("photographer", ""), "generic": True}
            for p in r.json().get("photos", [])]
