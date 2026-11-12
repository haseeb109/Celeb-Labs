# brain/hive.py — Hive provider serving DeepSeek models.
# Same OpenAI-style chat format; base URL can be overridden with HIVE_BASE_URL.
# Key lives in ~/.config/umf/hive.env.
import os
from .openai_compat import OpenAICompat


class Hive(OpenAICompat):
    name = "hive"
    base_url = os.environ.get("HIVE_BASE_URL", "https://api.thehive.ai/api/v3")
