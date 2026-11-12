# brain/ — the LLM layer: provider interface (llm.py), providers, repair loop (repair.py).
# The brain writes; code validates. The brain never decides legality (Section 6).
# Use `run_pass(brain, pass_name, messages, validator)` everywhere.
from .llm import get_brain, Provider, Completion, BrainError, NeedsManual, NeedsReview  # noqa
from .repair import run_pass, extract_json  # noqa
