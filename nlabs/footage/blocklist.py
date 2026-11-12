# footage/blocklist.py — Rule F7: never use major news/media channels or their re-uploads.
# Built-in names + channel IDs are constants; footage/blocklist.json can only ADD entries.
# Heuristics catch unknown news channels; OCR brand hits (F6 scan) also reject clips.
from __future__ import annotations

import json
import re
from pathlib import Path

BUILTIN_NAMES = [
    "CNN", "CNN-News18", "Fox News", "Fox Business", "MSNBC", "NBC News", "NBC", "ABC News", "CBS News", "CBS",
    "PBS NewsHour", "BBC", "BBC News", "Sky News", "ITV News", "Channel 4 News", "Reuters", "Associated Press",
    "AP", "AFP", "AFP News Agency", "Bloomberg", "Bloomberg Television", "Bloomberg Originals", "Bloomberg Quicktake",
    "CNBC", "CNBC International", "CNBC-TV18", "CNBC Television", "Yahoo Finance", "Wall Street Journal", "WSJ",
    "The Wall Street Journal", "New York Times", "The New York Times", "Washington Post", "The Washington Post",
    "The Guardian", "Guardian News", "Financial Times", "The Economist", "Al Jazeera", "Al Jazeera English",
    "DW News", "DW", "FRANCE 24", "FRANCE 24 English", "Euronews", "TRT World", "WION", "NDTV", "India Today",
    "Times Now", "ABC News (Australia)", "ABC News In-depth", "CBC News", "CBC News: The National", "Global News",
    "CTV News", "TMZ", "Inside Edition", "Entertainment Tonight", "Access Hollywood", "E! News", "People",
    "Variety", "The Hollywood Reporter", "Forbes", "Forbes Breaking News", "Business Insider", "Insider",
    "Fortune", "Fortune Magazine", "CNET", "The Verge", "Vox", "Vice News", "VICE News", "NowThis", "NowThis News",
    "AP Archive", "Associated Press Archive", "British Pathé", "British Pathe", "Getty Images", "Storyful",
    "Newsflare", "ViralHog", "Jukin Media", "Jukinvideo", "Sky News Australia", "NBC Bay Area", "LiveNOW from FOX",
    "FOX 5", "ABC7", "CBS Mornings", "Good Morning America", "TODAY", "60 Minutes", "Face the Nation",
    "Meet the Press", "Bloomberg Technology", "Yahoo News", "Newsmax", "NewsNation", "The Telegraph",
    "Daily Mail", "The Sun", "The Independent", "Reuters Plus",
]
BUILTIN_IDS = [
    "UCupvZG-5ko_eiXAupbDfxWw",  # CNN
    "UCXIJgqnII2ZOINSWNOGFThA",  # Fox News
    "UCaXkIU1QidjPwiAYu6GcHjg",  # MSNBC
    "UCeY0bbntWzzVIaj2z3QigXg",  # NBC News
    "UCBi2mrWuNuyYy4gbM6fU18Q",  # ABC News
    "UC8p1vwvWtl6T73JiExfWs1g",  # CBS News
    "UC16niRr50-MSBwiO3YDb3RA",  # BBC News
    "UCoMdktPbSTixAyNGwb-UYkQ",  # Sky News
    "UChqUTb7kYRX8-EiaN3XFrSQ",  # Reuters
    "UC52X5wxOL_s5yw0dQk7NtgA",  # Associated Press
    "UCIALMKvObZNtJ6AmdCLP7Lg",  # Bloomberg Television
    "UCvJJ_dzjViJCoLf5uKUTwoA",  # CNBC
    "UCrp_UI8XtuYfpiqluWLD7Lw",  # CNBC Television
    "UCEAZeUIeJs0IjQiqTCdVSIg",  # Yahoo Finance
    "UCK7tptUDHh-RYDsdxO1-5QQ",  # Wall Street Journal
    "UCqnbDFdCpuN8CMEg0VuEBqA",  # New York Times
    "UCHd62-u_v4DvJ8TCFtpi4GA",  # Washington Post
    "UCHpw8xwDNhU9gdohEcJu4aA",  # The Guardian
    "UCNye-wNBqNL5ZzHSJj3l8Bg",  # Al Jazeera English
    "UCknLrEdhRCp1aegoMqRaCZg",  # DW News
    "UCQfwfsi5VrQ8yKZ-UWmAEFg",  # FRANCE 24 English
    "UCSrZ3UV4jOidv8ppoVuvW9Q",  # euronews
    "UC7fWeaHhqgM4Ry-RMpM2YYw",  # TRT World
    "UC_gUM8rL-Lrg6O3adPW9K1g",  # WION
    "UCZFMm1mMw0F81Z37aaEzTUA",  # NDTV
    "UCYPvAwZP8pZhSMW8qs7cVCw",  # India Today
    "UCuFFtHWoLl5fauMMD5Ww2jA",  # CBC News
    "UChLtXXpo4Ge1ReTEboVvTDg",  # Global News
    "UCi7GJNg51C3jgmYTUwqoUXA",  # CTV News
    "UCa_UmFUZRBzFqs8ZImLXJnA",  # TMZ (best known id)
    "UCVcQH8A634mauPrGbWs7QlQ",  # Inside Edition
    "UCdtXPiqI2cLorKaPrfpKc4g",  # Entertainment Tonight
    "UCddiUEpeqJcYeBxX1IVBKvQ",  # The Verge
    "UCLXo7UDZvByw2ixzpQCufnA",  # Vox
    "UCZaT_X_mc0BI-djXOlfhqWQ",  # VICE News
    "UCcyq283he07B7_KUX07mmtA",  # Business Insider
    "UCg40OxZ1GYh3u3jBntB6DLg",  # Forbes Breaking News
    "UCOmcA3f_RrH6b9NmcNa4tdg",  # CNET
    "UCfdNM3NAhaBOXCafH7krzrA",  # The Hollywood Reporter (best known id)
]
BRAND_TOKENS = ["CNN", "FOX NEWS", "FOX BUSINESS", "MSNBC", "NBC", "ABC NEWS", "CBS", "BBC", "SKY NEWS", "REUTERS",
                "BLOOMBERG", "CNBC", "YAHOO FINANCE", "AL JAZEERA", "DW NEWS", "FRANCE 24", "EURONEWS", "TRT",
                "WION", "NDTV", "TMZ", "NEWSMAX", "NEWSNATION", "AP ", "AFP", "WSJ", "ITV", "CTV", "PBS"]
NEWS_WORDS = re.compile(r"\b(news|tv|network|broadcast(ing)?|media group|channel \d+)\b", re.I)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


class Blocklist:
    def __init__(self, user_file: Path | None = None):
        names, ids = list(BUILTIN_NAMES), list(BUILTIN_IDS)
        user_file = user_file or Path(__file__).with_name("blocklist.json")
        if user_file.exists():
            try:
                u = json.loads(user_file.read_text(encoding="utf-8"))
                names += u.get("names", [])   # additions only — built-ins are never removed
                ids += u.get("channel_ids", [])
            except json.JSONDecodeError:
                pass
        self.names = {_norm(n) for n in names}
        self.ids = set(ids)

    def check(self, channel: str = "", channel_id: str = "", subscribers: int | None = None,
              description: str = "", category: str = "") -> str | None:
        """Return a rejection reason, or None if the channel is allowed."""
        if channel_id and channel_id in self.ids:
            return f"blocklisted channel id {channel_id}"
        n = _norm(channel)
        if n and n in self.names:
            return f"blocklisted channel name '{channel}'"
        for b in self.names:
            if (len(b) >= 4 and n.startswith(b) and len(n) - len(b) <= 12) or (len(b) >= 8 and n.startswith(b)):
                return f"blocklisted brand prefix '{channel}'"
        text = f"{channel} {description[:300]}"
        if NEWS_WORDS.search(channel or "") and (subscribers or 0) > 500_000:
            return f"heuristic: news-like channel name with {subscribers} subscribers"
        if (category or "").lower() in ("news & politics", "news") and (subscribers or 0) > 500_000 \
                and NEWS_WORDS.search(text):
            return "heuristic: large News & Politics channel"
        return None

    def title_reupload(self, title: str) -> str | None:
        """Re-upload heuristic: a title that names a news brand ('… / CNBC Full Interview') — F7 covers re-uploads."""
        b = self.brand_in_text(title or "")
        if b and b not in ("AP", "TRT", "AFP", "PBS", "ITV", "CTV"):   # short tokens are too ambiguous in titles
            return f"title names news brand '{b}' (likely re-upload of news footage)"
        return None

    @staticmethod
    def brand_in_text(text: str) -> str | None:
        """OCR hit → brand name (used by the watermark scan, F6/F7)."""
        up = f" {(text or '').upper()} "
        for b in BRAND_TOKENS:
            if re.search(r"(?<![A-Z])" + re.escape(b.strip()) + r"(?![A-Z])", up):
                return b.strip()
        return None
