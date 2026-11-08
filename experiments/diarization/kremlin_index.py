"""Index kremlin.ru transcripts: speakers per event and video links.

kremlin.ru materials are published under CC BY 4.0. Each transcript page marks
every turn with the speaker in bold ("<p><b>В.Путин:</b> ...") and links the
event video. These events are unlikely to be in diarization training sets
(those are mostly English / Chinese meetings, broadcasts and telephone calls),
so they serve as an unseen Russian test set.

Usage: python kremlin_index.py OUT_DIR [PAGES]
Writes OUT_DIR/index.json: one entry per transcript with its id, title,
speaker turn counts and video URLs.
"""
import html
import json
import re
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

BASE = "http://kremlin.ru"
USER_AGENT = {"User-Agent": "Mozilla/5.0"}


def fetch(url):
    """Download one page as text (the site serves UTF-8)."""
    request = urllib.request.Request(url, headers=USER_AGENT)
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", "replace")


def parse_turns(page):
    """Return [(speaker, text)] from a transcript page.

    A turn starts at a paragraph whose bold prefix ends with ":"; the
    following paragraphs without a bold name belong to the same speaker.
    """
    article = page.split('class="read__internal_content"', 1)[-1]
    article = article.split('class="read__bottommeta', 1)[0]
    turns = []
    for paragraph in re.findall(r"<p>(.*?)</p>", article, re.S):
        name_match = re.match(r"\s*<b>\s*([^<]{2,60}?)\s*:?\s*</b>\s*:?(.*)", paragraph, re.S)
        if name_match and re.match(r"^[А-ЯЁA-Z]\.\s?[А-ЯЁA-Z]", name_match.group(1)):
            speaker = name_match.group(1).strip().rstrip(":").replace(" ", "")
            text = name_match.group(2)
            turns.append([speaker, ""])
        elif turns:
            text = paragraph
        else:
            continue  # introduction before the first named turn
        text = html.unescape(re.sub(r"<[^>]+>", " ", text))
        turns[-1][1] = (turns[-1][1] + " " + " ".join(text.split())).strip()
    return [(speaker, text) for speaker, text in turns if text]


def video_links(page):
    """Return the event's video URLs (low and high quality) found on the page."""
    return sorted(set(re.findall(r"https?://static\.kremlin\.ru/media/events/video/ru/video_(?:low|high)/\w+\.mp4", page)))


def main():
    out_dir = Path(sys.argv[1])
    pages = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for page_number in range(1, pages + 1):
        listing = fetch(f"{BASE}/events/president/transcripts/page/{page_number}")
        ids = list(dict.fromkeys(re.findall(r'href="/events/president/transcripts/(\d+)"', listing)))
        for event_id in ids:
            page = fetch(f"{BASE}/events/president/transcripts/{event_id}")
            title = html.unescape(re.search(r"<title[^>]*>(.*?)</title>", page, re.S).group(1)).strip()
            turns = parse_turns(page)
            entries.append({
                "id": event_id,
                "title": title,
                "speakers": Counter(speaker for speaker, _ in turns).most_common(),
                "turns": len(turns),
                "words": sum(len(text.split()) for _, text in turns),
                "videos": video_links(page),
            })
            (out_dir / f"{event_id}.turns.json").write_text(
                json.dumps(turns, ensure_ascii=False, indent=0), encoding="utf-8")
            time.sleep(0.5)  # be polite to the site
    (out_dir / "index.json").write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
    for entry in entries:
        print(entry["id"], len(entry["speakers"]), entry["turns"], entry["words"], len(entry["videos"]), entry["title"][:70])


if __name__ == "__main__":
    main()
