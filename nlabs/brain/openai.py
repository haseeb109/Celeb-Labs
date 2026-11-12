# brain/openai.py — OpenAI provider (optional).
# Uses the standard chat-completions endpoint with JSON mode.
# Key lives in ~/.config/umf/openai.env.
from .openai_compat import OpenAICompat


class OpenAI(OpenAICompat):
    name = "openai"
    base_url = "https://api.openai.com/v1"
