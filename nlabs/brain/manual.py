# brain/manual.py — "manual" brain: you are the LLM.
# Each call writes the prompt to work/<run>/manual/<pass>_<n>.prompt.md and reads
# <pass>_<n>.response.json if you pasted one there; otherwise the run pauses (resumable).
import sys
from pathlib import Path
from .llm import Provider, Completion, NeedsManual


class Manual(Provider):
    name = "manual"

    def __init__(self, folder: Path | None = None, interactive: bool | None = None, **kw):
        super().__init__(model="manual", **kw)
        self.folder = Path(folder or ".")
        self.folder.mkdir(parents=True, exist_ok=True)
        self.counter: dict[str, int] = {}
        self.interactive = sys.stdin.isatty() if interactive is None else interactive

    def complete(self, messages, json_schema=None, max_tokens=4000, temperature=0.4, pass_name="pass"):
        n = self.counter.get(pass_name, 0) + 1
        self.counter[pass_name] = n
        stem = f"{pass_name}_{n}"
        prompt = "\n\n".join(f"## {m['role'].upper()}\n{m['content']}" for m in messages)
        (self.folder / f"{stem}.prompt.md").write_text(prompt, encoding="utf-8")
        resp = self.folder / f"{stem}.response.json"
        if resp.exists():
            return Completion(text=resp.read_text(encoding="utf-8"), model="manual")
        if self.interactive:
            print(f"\n[manual brain] Prompt saved to {self.folder / (stem + '.prompt.md')}")
            print("Paste the JSON reply, then a line with only END:")
            lines = []
            for line in sys.stdin:
                if line.strip() == "END":
                    break
                lines.append(line)
            text = "".join(lines)
            resp.write_text(text, encoding="utf-8")
            return Completion(text=text, model="manual")
        raise NeedsManual(f"Manual brain: answer {self.folder / (stem + '.prompt.md')} in {resp.name}, then resume.")
