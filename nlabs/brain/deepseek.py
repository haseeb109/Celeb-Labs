# brain/deepseek.py — DeepSeek API provider (the default brain).
# OpenAI-compatible endpoint at https://api.deepseek.com; model from config
# (deepseek-chat by default). Cheap and good enough with the gold examples.
from .openai_compat import OpenAICompat


class DeepSeek(OpenAICompat):
    name = "deepseek"
    base_url = "https://api.deepseek.com"
