# images/pixabay.py — Pixabay API for generic B-roll photos (fallback after Pexels).
# Optional key in ~/.config/umf/pixabay.env. Pixabay Content License.
# Generic only (no people claimed as the subject).
def search(query, key, n=10, client=None):
    from ..util import http_client
    c = client or http_client()
    r = c.get("https://pixabay.com/api/", params={"key": key, "q": query, "per_page": max(3, n), "image_type": "photo"})
    r.raise_for_status()
    return [{"source": "pixabay", "url": h["largeImageURL"], "page": h["pageURL"], "title": h.get("tags", ""),
             "license": "Pixabay Content License", "author": h.get("user", ""), "generic": True}
            for h in r.json().get("hits", [])]
