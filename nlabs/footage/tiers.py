# footage/tiers.py — source tiers: A public domain/government, B licensed, C other, or BLOCKED.
# Tier A allow-list comes from styles/<style>/sources_tierA.json; Tier B = Creative Commons
# (yt-dlp `license`) or Wikimedia CC/PD or the owner's licensed folder.
from __future__ import annotations

import json
from pathlib import Path

from .blocklist import Blocklist


def load_tier_a(style_dir: Path) -> dict:
    p = style_dir / "sources_tierA.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"channels": []}


def classify(meta: dict, tier_a: dict, blocklist: Blocklist, official_ids: set[str] | None = None) -> tuple[str, str]:
    """Return (tier, license_note). tier in {A,B,C,BLOCKED}."""
    reason = blocklist.check(meta.get("channel", ""), meta.get("channel_id", ""),
                             meta.get("channel_follower_count"), meta.get("description", ""),
                             (meta.get("categories") or [""])[0] if meta.get("categories") else "")
    if reason:
        return "BLOCKED", reason
    cid, ch = meta.get("channel_id", ""), (meta.get("channel") or "").lower()
    for c in tier_a.get("channels", []):
        if cid and cid == c.get("id") or ch and ch == c.get("name", "").lower():
            return "A", c.get("license", "U.S. federal government work (public domain)")
    lic = (meta.get("license") or "").lower()
    if "creative commons" in lic or meta.get("owner_licensed") or meta.get("wikimedia_license"):
        return "B", meta.get("license") or meta.get("wikimedia_license") or "owner-licensed"
    if official_ids and cid in official_ids:
        return "C", "subject's official channel (short excerpt)"
    return "C", "short excerpt (commentary/news reporting)"
