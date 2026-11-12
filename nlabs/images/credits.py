# images/credits.py — builds image_credits.txt (title, author, license, URL, modified).
# The same lines go into the description's credits section.
def credit_line(im: dict) -> str:
    mod = " (modified)" if im.get("modified") else ""
    return f"\"{im.get('title', 'image')[:80]}\" by {im.get('author') or 'unknown'} — {im.get('license')} — " \
           f"{im.get('page') or im.get('url')}{mod}"


def write(images: list[dict], path):
    lines = [credit_line(i) for i in images if i.get("source") not in ("still",)]
    stills = [i for i in images if i.get("source") == "still"]
    if stills:
        lines.append("")
        lines.append("Stills extracted from footage credited in footage_log.csv:")
        lines += [f"  frame from {s['channel']} — {s['url']} @ {s['t']:.1f}s" for s in stills]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return lines
