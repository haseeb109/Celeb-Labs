# images/official_photos.py — press photos from official newsrooms, ONLY with editorial terms.
# The owner lists them in assets/press_photos/press_photos.json (url, terms, credit);
# the tool never scrapes newsrooms on its own because terms must be read by a human.
import json
from ..paths import ASSETS


def load():
    p = ASSETS / "press_photos" / "press_photos.json"
    if not p.exists():
        return []
    return [x | {"source": "press", "license": x.get("terms", "editorial use per press page")}
            for x in json.loads(p.read_text(encoding="utf-8")) if x.get("terms")]
