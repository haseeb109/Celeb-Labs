# script/schema.py — shapes of outline.json and script.json (for prompts and docs).
# Kept as plain dicts so cheaper models can read them in the prompt.
# The validator (validate_script.py) is the real enforcement.
SEGMENT_EXAMPLE = {
    "id": "s042", "chapter": 3, "kind": "vo",
    "text": "In a statement, the company said the board accepted his resignation.",
    "fact_ids": ["F007"], "attribution": "company statement",
    "visual": {"intent": "subject_reacting", "prefer": ["footage", "statement_card"], "keywords": ["podium"]},
    "retention": "none",
}
OUTLINE_EXAMPLE = {
    "title_working": "...",
    "chapters": [{"n": 1, "title": "Who he is", "goal": "...", "fact_ids": ["F001"], "official_cards": [],
                  "footage_ideas": ["keynote 2024"]}],
    "comment_prompt": {"question": "...", "answer_fact_ids": ["F010"]},
}
