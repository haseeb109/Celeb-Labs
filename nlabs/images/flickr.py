# images/flickr.py — Flickr CC search (license filter 4,7,8,9,10: BY, no known restrictions,
# US gov, CC0, PDM). Downloads use a browser User-Agent + Referer; run on a home connection.
# Needs a free Flickr API key in ~/.config/umf/flickr.env.
LICENSES = {"4": "CC BY 2.0", "7": "No known copyright restrictions", "8": "United States Government Work",
            "9": "CC0", "10": "Public Domain Mark"}


def search(query, key, n=10, client=None):
    from ..util import http_client
    c = client or http_client()
    r = c.get("https://api.flickr.com/services/rest/", params={
        "method": "flickr.photos.search", "api_key": key, "text": query, "license": "4,7,8,9,10",
        "extras": "license,owner_name,url_l,url_o", "per_page": n, "format": "json", "nojsoncallback": 1,
        "sort": "relevance"})
    r.raise_for_status()
    out = []
    for p in r.json().get("photos", {}).get("photo", []):
        u = p.get("url_l") or p.get("url_o")
        if u:
            out.append({"source": "flickr", "url": u, "page": f"https://www.flickr.com/photos/{p['owner']}/{p['id']}",
                        "title": p.get("title", ""), "license": LICENSES.get(str(p.get("license")), "CC"),
                        "author": p.get("ownername", ""), "referer": "https://www.flickr.com/"})
    return out
