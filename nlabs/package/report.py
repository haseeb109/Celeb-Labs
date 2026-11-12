# package/report.py — run_report.md: readable summary of the run: stations and timings, pool
# size (F3), ratios, QC checks, skipped sources, manual actions needed, cost.
from __future__ import annotations

from ..log import TIMINGS


def write(rp, topic, qc=None, pool_stats=None, plan=None, research_errors=None, manual=None, usage=None, extra=None):
    L = [f"# Run report — {topic}", "", f"Run id: `{rp.run_id}`", ""]
    if TIMINGS:
        L += ["## Station timings", ""] + [f"- {k}: {v:.1f}s" for k, v in TIMINGS.items()] + [""]
    if pool_stats:
        s = pool_stats
        L += ["## Footage pool (F3)", "",
              f"- Pool: {s.get('pool_clips')} clips, {s.get('pool_seconds')} s from {s.get('pool_sources')} source videos",
              f"- Needed: {s.get('need_seconds')} s → ratio {s.get('pool_ratio')}× (target ≥ 3×, ≥ 8 sources) — "
              f"{'OK' if s.get('pool_ok') else 'BELOW TARGET'}",
              f"- Tiers: {s.get('tiers')}", f"- Face backend: {s.get('face_backend')} · reference: {s.get('reference')}",
              f"- Candidates found: {s.get('candidates')} · windows downloaded: {s.get('windows')}",
              f"- Rejected videos/channels: {len(s.get('rejected', []))} · rejected windows: {len(s.get('windows_rejected', []))}", ""]
        seen, blk = set(), []
        for r in s.get("rejected", []):
            if r.get("id") not in seen and any(k in str(r.get("reason", "")) for k in ("blocklist", "heuristic", "brand")):
                seen.add(r.get("id"))
                blk.append(r)
        if blk:
            L += ["### Blocked by F7 (news channels)", ""] + [f"- {r.get('channel')} ({r.get('id')}): {r.get('reason')}" for r in blk[:40]] + [""]
        wr = s.get("windows_rejected", [])
        if wr:
            L += ["### Windows rejected (F6 scan / download)", ""] + [f"- {w.get('video_id')} @ {w.get('window_start', w.get('start'))}: "
                                                                     f"{w.get('reject') or w.get('reason')}" for w in wr[:40]] + [""]
        if s.get("candidate_list"):
            L += ["### Candidate videos (after blocklist)", "", "| id | channel | title | rel |", "|---|---|---|---|"] + \
                 [f"| {c['id']} | {c['channel']} | {c['title'].replace('|', '/')} | {c['relevance']} |" for c in s["candidate_list"]] + [""]
        if s.get("errors"):
            L += ["### Footage errors", ""] + [f"- {e}" for e in s["errors"][:20]] + [""]
    if plan:
        r = plan["ratios"]
        L += ["## Edit plan", "", f"- Runtime {plan['runtime']} s · {plan['shots']} shots · avg {plan['avg_shot']} s · "
              f"max footage shot {plan['max_footage_shot']} s",
              f"- F1: footage {r['footage']:.1%} (≥65%) · animation {r['animation']:.1%} (≤20%) · text {r['text']:.1%} (≤15%)",
              f"- Planner attempts: {[a['mode'] + (' OK' if not a['errors'] else ' ' + '; '.join(a['errors'])) for a in plan.get('attempts', [])]}", ""]
    if qc:
        L += ["## QC", "", f"**Overall: {qc['overall']}**", ""] + [f"- {'✅' if v else '❌'} {k}" for k, v in qc["checks"].items()] + [""]
    if research_errors:
        L += ["## Research problems", ""] + [f"- {e}" for e in research_errors] + [""]
    if manual:
        L += ["## Manual actions needed", ""] + [f"- {m}" for m in manual] + [""]
    if extra:
        L += extra
    if usage:
        L += ["## Cost", "", "```", usage.report(), "```"]
    rp.o("run_report.md").write_text("\n".join(L), encoding="utf-8")
