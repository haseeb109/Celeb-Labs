# script/outline.py — outline pass: chapters with goals, facts, official cards, footage ideas.
# Validated in code (chapter count, fact ids exist, every official card is placed).
# Output: work/<run>/outline.json.
import json

from ..brain import run_pass


def validate_outline(d, ledger, official_cards, n_chapters):
    if not isinstance(d, dict) or not isinstance(d.get("chapters"), list):
        return ['Expected {"chapters":[...], "comment_prompt":{...}}']
    errs = []
    ids = ledger.by_id()
    if not (n_chapters - 2 <= len(d["chapters"]) <= n_chapters + 1):
        errs.append(f"need about {n_chapters} chapters, got {len(d['chapters'])}")
    placed = set()
    for c in d["chapters"]:
        for fid in c.get("fact_ids", []):
            if fid not in ids:
                errs.append(f"chapter {c.get('n')}: fact_id {fid} not in ledger")
            placed.add(fid)
        placed.update(c.get("official_cards", []))
    for oc in official_cards:
        if oc["fact_id"] not in placed:
            errs.append(f"official card {oc['fact_id']} must be placed in a chapter (S1)")
    if not d.get("comment_prompt", {}).get("question"):
        errs.append("comment_prompt.question missing")
    return errs


def run_outline(topic, subject, ledger, official, cfg, brain, minutes, prompt_text):
    n = cfg.style.get("chapters", 9) if minutes >= 10 else max(1, round(minutes / 2.2))
    payload = {"topic": topic, "subject": subject, "minutes": minutes, "chapters": n,
               "narrative": cfg.style.get("narrative", []), "ledger": ledger.facts,
               "official_cards": official.get("cards", [])}
    return run_pass(brain, "outline", [{"role": "system", "content": prompt_text},
                                       {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                    lambda d: validate_outline(d, ledger, official.get("cards", []), n),
                    cfg.get("brain_attempts", 3), cfg.get("max_repair_rounds", 3), 4000)
