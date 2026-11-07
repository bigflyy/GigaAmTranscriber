"""The window's list of transcribed files, kept between sessions.

Each finished file is one JSON file in the history folder (paths.history_dir()):
where the audio was, how it ended, which transcript files were written, and the
whole transcript with word times, so the text shows and more formats can be
written after a restart without recognising the file again. Removing a file from
the list deletes its entry here, never the transcript files beside the audio.

Files are read once at start-up. A damaged entry is skipped, not fatal.
"""

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import tempfile
import time
import uuid

from .engine import Segment, Transcript, Word
from .paths import replace_file

VERSION = 1


@dataclass
class Entry:
    """One remembered file. key is the entry's file name without .json."""
    key: str
    path: Path
    state: str                    # "done" or "cancelled"
    transcript: Transcript
    written: dict = field(default_factory=dict)   # format -> Path
    duration: float = None
    elapsed: float = 0.0
    speech_seconds: float = None
    saved_at: float = 0.0         # time.time() of the last save; orders the list


def new_key():
    return uuid.uuid4().hex


def _transcript_from(data):
    segments = [Segment(start=s["start"], end=s["end"], text=s["text"],
                        words=[Word(**word) for word in s.get("words", [])])
                for s in data.get("segments", [])]
    return Transcript(**{**data, "segments": segments})


class History:
    def __init__(self, folder):
        self.folder = Path(folder)

    def load(self):
        """All readable entries, oldest first."""
        entries = []
        if not self.folder.is_dir():
            return entries
        for path in self.folder.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("version") != VERSION:
                    continue
                entries.append(Entry(
                    key=path.stem, path=Path(data["path"]), state=data["state"],
                    transcript=_transcript_from(data["transcript"]),
                    written={fmt: Path(value) for fmt, value in data.get("written", {}).items()},
                    duration=data.get("duration"), elapsed=data.get("elapsed", 0.0),
                    speech_seconds=data.get("speech_seconds"), saved_at=data.get("saved_at", 0.0)))
            except (OSError, ValueError, KeyError, TypeError):
                continue  # a damaged or foreign file: leave it, show the rest
        entries.sort(key=lambda entry: entry.saved_at)
        return entries

    def save(self, entry):
        """Write one entry atomically. Raises OSError if the folder cannot be written."""
        if not entry.saved_at:
            entry.saved_at = time.time()
        data = {
            "version": VERSION, "path": str(entry.path), "state": entry.state,
            "written": {fmt: str(path) for fmt, path in entry.written.items()},
            "duration": entry.duration, "elapsed": entry.elapsed, "speech_seconds": entry.speech_seconds,
            "saved_at": entry.saved_at, "transcript": asdict(entry.transcript),
        }
        self.folder.mkdir(parents=True, exist_ok=True)
        target = self.folder / f"{entry.key}.json"
        handle, temporary = tempfile.mkstemp(dir=self.folder, prefix=target.name + ".", suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(data, stream, ensure_ascii=False)
            replace_file(temporary, target)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

    def delete(self, key):
        (self.folder / f"{key}.json").unlink(missing_ok=True)
