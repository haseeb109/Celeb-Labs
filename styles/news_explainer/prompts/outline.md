You outline a {minutes}-minute news-explainer video. Narrative: cold open hook (45–60 s) → title →
Ch1 background → Ch2 first report → Ch3 official statement → Ch4 reactions → Ch5 escalation →
Ch6 the decision/event → Ch7 investigations/officials → Ch8 money & stakes (HYPOTHETICAL labels) →
Ch9 what happens next + what we still don't know → outro (answer the comment prompt, subscribe).
Use only ledger facts (by fact_id). Place EVERY official card (official_cards[].fact_id) in a chapter.
Reply JSON only:
{"title_working":"...","chapters":[{"n":1,"title":"...","goal":"...","fact_ids":["F001"],"official_cards":["F007"],
"footage_ideas":["keynote 2024","campus"]}],"comment_prompt":{"question":"...","answer_fact_ids":["F010"]}}
