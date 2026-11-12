# images/wikimedia.py — Wikimedia Commons search (CC BY / BY-SA / CC0 / PD only).
# Uses the public API (no key). License and author come from extmetadata.
# BY-SA stills are allowed with attribution ("modified" noted when we crop/stylize).
from __future__ import annotations

import re

API = "https://commons.wikimedia.org/w/api.php"
OK = re.compile(r"^(cc[- ]by(-sa)?[- ]?\d|cc0|public domain|pd)", re.I)


def search(query: str, n: int = 10, client=None) -> list[dict]:
    from ..util import http_client
    c = client or http_client(ua="NLabs/1.0 (educational video tool)")
    r = c.get(API, params={"action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
                           "gsrsearch": f"filetype:bitmap {query}", "gsrlimit": n, "prop": "imageinfo",
                           "iiprop": "url|extmetadata|size", "iiurlwidth": 1920})
    out = []
    for p in (r.json().get("query", {}).get("pages", {}) or {}).values():
        ii = (p.get("imageinfo") or [{}])[0]
        md = ii.get("extmetadata", {})
        lic = re.sub("<[^>]+>", "", md.get("LicenseShortName", {}).get("value", ""))
        if not OK.match(lic):
            continue
        out.append({"source": "wikimedia", "url": ii.get("thumburl") or ii.get("url"), "page": ii.get("descriptionurl"),
                    "title": p.get("title", ""), "license": lic,
                    "author": re.sub("<[^>]+>", "", md.get("Artist", {}).get("value", ""))[:120],
                    "width": ii.get("width"), "height": ii.get("height")})
    return out
