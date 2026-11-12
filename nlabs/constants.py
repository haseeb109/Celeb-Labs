# constants.py — LOCKED RULE VALUES (Section 3 of the build spec).
# These numbers are hard limits enforced in code. Config may only make them
# STRICTER (smaller caps / higher minimums); `tighten()` guarantees that.

MAX_CLIP_SECONDS = 5.0            # F2: no third-party clip longer than this on screen
FOOTAGE_MIN_RATIO = 0.65          # F1: >= 65 % real footage / photos
ANIMATION_MAX_RATIO = 0.20        # F1: <= 20 % motion graphics
TEXT_CARDS_MAX_RATIO = 0.15       # F1: <= 15 % text-only cards
POOL_MULTIPLIER_MIN = 3.0         # F3: pool >= 3x footage seconds needed
MIN_SOURCE_VIDEOS = 8             # F3
PER_SOURCE_MAX_CLIPS = 4          # F4 (Tier B/C)
PER_SOURCE_MAX_SECONDS = 15.0     # F4 (Tier B/C)
WATERMARK_CROP_MIN_AREA = 0.70    # F6: crop must keep >= 70 % of the frame
FACE_THRESHOLD_COSINE = 0.45      # F8 minimum similarity (insightface / SFace)
TTS_CONFIRM_CHARS = 5000          # V1: stop before TTS above this unless confirmed
STATEMENT_CARD_MAX_CHARS = 220    # S1: longer statements split across cards

W, H, FPS = 1920, 1080, 30
AUDIO_RATE = 48000
TARGET_LUFS = -14.0

# Shot categories used by the F1 ratio validator
CAT_FOOTAGE = "footage"       # real footage, real photos, soundbites (any treatment)
CAT_ANIMATION = "animation"   # charts, maps, timelines, counters
CAT_TEXT = "text"             # text-only cards on plain backgrounds


class LockedRuleError(AssertionError):
    """Raised whenever a locked rule (Section 3) would be broken."""


def tighten(name: str, config_value, locked_value, stricter: str):
    """Return the config value only if it is at least as strict as the locked value.
    stricter='lower' means smaller numbers are stricter (caps); 'higher' the opposite."""
    if config_value is None:
        return locked_value
    v = type(locked_value)(config_value)
    if stricter == "lower":
        return min(v, locked_value)
    return max(v, locked_value)
