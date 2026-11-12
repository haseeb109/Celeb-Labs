# audio/loudness.py — final loudness: two-pass ffmpeg loudnorm to I=−14, TP=−1.5, LRA=11,
# plus a measurement helper used by QC.
import json
import re

from ..util import ffmpeg_bin
import subprocess


def measure(path) -> dict:
    p = subprocess.run([ffmpeg_bin(), "-hide_banner", "-i", str(path), "-af",
                        "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", p.stderr, re.S)
    return json.loads(m.group(0)) if m else {}


def normalize(src, dst, target=-14.0):
    m = measure(src)
    if m and m.get("input_i") not in (None, "-inf"):
        af = (f"loudnorm=I={target}:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
              f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    else:
        af = f"loudnorm=I={target}:TP=-1.5:LRA=11"
    subprocess.run([ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-af", af,
                    "-ar", "48000", "-ac", "2", str(dst)], check=True)
    return measure(dst)
