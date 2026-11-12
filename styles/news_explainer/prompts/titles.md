Write YouTube packaging for a factual news explainer. Input: subject, topic, confirmed facts.
Return JSON only: {"titles":[{"style":"curiosity","text":"..."},{"style":"consequence",...},{"style":"number",...},
{"style":"question",...},{"style":"contrarian",...}], "summary":"2–3 sentence neutral description",
"tags":["15 tags"], "pinned_comment":"one engaging question"}
Each title ≤ 70 characters, truthful (no claims beyond confirmed facts), no ALL CAPS sentences.
