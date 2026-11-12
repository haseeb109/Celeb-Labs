# edit/treatments.py — footage treatments (Rule F5) and their rotation.
# full, punch_in (1.00→1.08), split, framed, pip (over blurred copy), bw, text_over.
# Rotation avoids repeating a treatment back-to-back and forces a change between shots of one source.
TREATMENTS = ["punch_in", "full", "framed", "split", "pip", "text_over", "full", "punch_in"]
DRAMATIC = "bw"


class Rotator:
    def __init__(self):
        self.i = 0
        self.last = None
        self.last_video = None

    def next(self, video_id: str | None, dramatic: bool = False, tier: str = "C", allow_split=True) -> str:
        if dramatic and self.last != DRAMATIC:
            t = DRAMATIC
        else:
            for _ in range(len(TREATMENTS)):
                t = TREATMENTS[self.i % len(TREATMENTS)]
                self.i += 1
                if t == self.last:
                    continue
                if t == "split" and not allow_split:
                    continue
                if video_id and video_id == self.last_video and t == self.last:
                    continue
                break
        # Tier C prefers transformative treatments (F5)
        if tier == "C" and t == "full":
            t = "framed" if self.last != "framed" else "text_over"
        self.last, self.last_video = t, video_id
        return t
