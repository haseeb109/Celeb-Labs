# brain/mock.py — scripted brain for tests and the offline end-to-end demo.
# Replies are queued per pass name (`queue(pass, text)`); a callable can build a
# reply from the messages. Never touches the network.
from .llm import Provider, Completion, BrainError


class MockBrain(Provider):
    name = "mock"

    def __init__(self, replies: dict | None = None, **kw):
        super().__init__(model="mock", **kw)
        self.replies = {k: list(v) if isinstance(v, list) else [v] for k, v in (replies or {}).items()}
        self.calls: list[tuple[str, list]] = []

    def queue(self, pass_name, reply):
        self.replies.setdefault(pass_name, []).append(reply)

    def complete(self, messages, json_schema=None, max_tokens=4000, temperature=0.4, pass_name=""):
        self.calls.append((pass_name, messages))
        q = self.replies.get(pass_name) or self.replies.get("*")
        if not q:
            raise BrainError(f"mock brain has no reply for pass '{pass_name}'")
        r = q.pop(0) if len(q) > 1 else q[0]
        text = r(messages) if callable(r) else r
        c = Completion(text=text, tokens_in=sum(len(m["content"]) for m in messages) // 4,
                       tokens_out=len(text) // 4, model="mock")
        self._record(pass_name, c)
        return c
