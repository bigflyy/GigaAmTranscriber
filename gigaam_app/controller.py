"""What the window shows: the file queue, the settings and the model status.

No GUI toolkit is used here, so the logic runs in tests with a fake worker.
The page (gigaam_app/web) calls the methods below through window.Api; every
change goes back to it as a message {seq, kind, data} through `send`.

Files run one at a time, in the order they were added. The model loads once
the page is ready and stays loaded between files; changing the model, device
or threads loads it again before the next file. A model that is not bundled
is downloaded first, after the user agrees.
"""

import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import itertools
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

from . import audio as audio_module, catalog, config, diarize, faster_whisper_model, fix
from .audio import wav_clip
from .audio_server import AudioServer
from .engine import MODELS, Transcript
from .history import Entry, new_key
from .outputs import FORMATS, llm_text, plain_text, timestamped_text, write_outputs
from .paths import downloads_dir, ffmpeg_executable

MEDIA_SUFFIXES = {".wav", ".mp3", ".m4a", ".ogg", ".opus", ".flac", ".aac", ".wma", ".mp4", ".mkv",
                  ".mov", ".avi", ".webm"}
FILE_DIALOG_TYPES = ("Аудио и видео (" + ";".join("*" + suffix for suffix in sorted(MEDIA_SUFFIXES)) + ")",
                     "Все файлы (*.*)")

DEVICES = (("Auto", "Авто"), ("GPU", "Видеокарта"), ("CPU", "Процессор"))
DEVICE_NAMES = {"GPU (DirectML)": "видеокарта (DirectML)", "GPU (CUDA)": "видеокарта (CUDA)",
                "GPU (Vulkan)": "видеокарта (Vulkan)", "CPU": "процессор",
                "CPU (faster-whisper)": "процессор, faster-whisper"}
FORMAT_LABELS = {"txt": "TXT", "timestamps": "TXT с таймкодами", "md": "Markdown (разделы по времени)",
                 "srt": "SRT (субтитры)", "json": "JSON (слова и время)",
                 "llm": "TXT для ИИ (сомнительные слова отмечены)"}
# Chips under a finished file: (format, short tag, label).
OUTPUT_CHIPS = (("txt", "TXT", "Текст"), ("timestamps", "TXT", "С таймкодами"), ("md", "MD", "Markdown"),
                ("srt", "SRT", "Субтитры"), ("json", "JSON", "Слова и время"), ("llm", "TXT", "Для ИИ"))
# Russian notes for the model choice; catalog descriptions are English.
MODEL_NOTES = {
    "RNNT": "Русский язык, пунктуация и заглавные буквы. Выбрана по умолчанию.",
    "CTC": "Русский язык, пунктуация и заглавные буквы. Немного быстрее RNNT.",
    "Whisper": "Whisper large-v3-turbo: 99 языков, английские термины пишет латиницей. "
               "Медленнее GigaAM примерно в 2,5 раза; на русском GigaAM обычно точнее.",
    # The download question of plan 08 C2 (the mock-up the owner saw); since C5 it also reads
    # the main text when Whisper is the chosen model (1.4x against whisper.cpp with the C6 patch,
    # lecture on the CPU; 2.8x against the unpatched whisper.cpp of plan 08 C4).
    "faster-whisper": "Whisper large-v3-turbo в формате faster-whisper (int8): на процессоре распознаёт "
                      "в 1,4 раза быстрее, а варианты для сомнительных слов ищет в 1,6-2 раза быстрее. "
                      "На видеокарте не используется.",
}
# Speech languages offered in the window for Whisper: (code, Russian name). The settings
# file and --language take any code Whisper knows; a code not listed here is still shown.
LANGUAGES = (("auto", "Определять автоматически"), ("ru", "Русский"), ("en", "Английский"),
             ("uk", "Украинский"), ("be", "Белорусский"), ("kk", "Казахский"), ("uz", "Узбекский"),
             ("de", "Немецкий"), ("fr", "Французский"), ("es", "Испанский"), ("it", "Итальянский"),
             ("pt", "Португальский"), ("pl", "Польский"), ("cs", "Чешский"), ("tr", "Турецкий"),
             ("ar", "Арабский"), ("he", "Иврит"), ("hi", "Хинди"), ("zh", "Китайский"),
             ("ja", "Японский"), ("ko", "Корейский"))

WAITING, RUNNING, DONE, CANCELLED, FAILED = "waiting", "running", "done", "cancelled", "failed"
# Models that give a reading when a selected part is recognised again (plan 03), in this order.
# Whisper only when it is downloaded.
REREAD_MODELS = ("RNNT", "CTC", "Whisper")
# The most speakers the window lets the user name as the known count (plan 07 C3).
MAX_SPEAKERS = 20
# Plan 07 H2: the speech search settings the window shows under "Дополнительно", with the
# range each may take. A line is at most 25 s: GigaAM reads about 25 s per call and Whisper
# hears a 30 s window. "max_duration" also sets vad_max_speech_s (a longer stretch of speech
# without a pause is cut there). The other speech search keys stay in the settings file.
SPEECH_LIMITS = {"vad_min_silence_ms": (100, 10000), "vad_threshold": (0.05, 0.95), "max_duration": (5.0, 25.0)}


# ---------------------------------------------------------------------- texts

def duration_text(seconds):
    """7:35, 48:12, 1:02:03."""
    total = int(round(seconds))
    hours, minutes, secs = total // 3600, total // 60 % 60, total % 60
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def about_text(seconds):
    """A rough time left: 'около 3 с', 'около 2 мин', 'около 1 ч 5 мин'."""
    seconds = max(1, int(round(seconds)))
    if seconds < 60:
        return f"около {seconds} с"
    minutes = int(round(seconds / 60))
    if minutes < 60:
        return f"около {minutes} мин"
    return f"около {minutes // 60} ч {minutes % 60} мин"


def times_text(number):
    """'в 87 раз', 'в 2 раза', 'в 21 раз': Russian plural after a number."""
    word = "раза" if number % 10 in (2, 3, 4) and number % 100 not in (12, 13, 14) else "раз"
    return f"в {number} {word}"


def places_word(number):
    """The Russian word "место" in the form that goes with number (1 место, 2 места, 5 мест)."""
    if number % 10 == 1 and number % 100 != 11:
        return "место"
    if 2 <= number % 10 <= 4 and not 12 <= number % 100 <= 14:
        return "места"
    return "мест"


def speakers_text(number):
    """'1 говорящий', '3 говорящих': the Russian word after a number (2-4 take the same form as 5)."""
    word = "говорящий" if number % 10 == 1 and number % 100 != 11 else "говорящих"
    return f"{number} {word}"


def size_text(size):
    megabytes = size / 1024 ** 2
    return f"{megabytes / 1024:.1f} ГБ" if megabytes >= 1024 else f"{megabytes:.0f} МБ"


def device_name(label):
    return DEVICE_NAMES.get(label, label)


# ---------------------------------------------------------------------- desktop helpers

def ffmpeg_header(path):
    """ffmpeg's header dump of a file (its stderr for "ffmpeg -i path"), or None when
    ffmpeg cannot be run or does not answer in time."""
    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        result = subprocess.run([ffmpeg_executable(), "-hide_banner", "-nostdin", "-i", str(path)],
                                capture_output=True, timeout=20, creationflags=flags)
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        return None
    return result.stderr


def has_sound(path):
    """False when ffmpeg finds no sound stream in a file (a txt, a document, a photo, a
    silent video). The answer comes from the streams, not the extension, so unusual
    media types (.ts, .3gp, .m4v) are accepted. True when ffmpeg cannot be asked: the
    file is let in and its job reports the problem."""
    header = ffmpeg_header(path)
    if header is None:
        return True
    return re.search(rb"Stream #\d+:\d+\S*: Audio:", header) is not None


def refused_text(names):
    """One notice for the files not added: at most three names, then how many more."""
    shown = ", ".join(names[:3]) + (f" и ещё {len(names) - 3}" if len(names) > 3 else "")
    return f"Не добавлено, в файле нет звука: {shown}"


def probe_duration(path):
    """Length of a media file in seconds from ffmpeg's header dump, or None."""
    header = ffmpeg_header(path)
    if header is None:
        return None
    match = re.search(rb"Duration: (\d+):(\d\d):(\d\d(?:\.\d+)?)", header)
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def open_path(path):
    """Open a file or folder with its default app."""
    if sys.platform == "win32":
        os.startfile(str(path))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def show_in_folder(path):
    """Open the folder of a file, with the file selected where the system allows it."""
    if sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", str(path)])
    else:
        open_path(Path(path).parent)


# ---------------------------------------------------------------------- state

@dataclass
class QueuedFile:
    id: str
    path: Path
    state: str = WAITING
    duration: float = None       # seconds, from probe_duration; None while unknown
    phase: str = ""              # what a running file is doing before progress starts
    progress: float = 0.0        # recognised fraction
    started: float = None        # clock() when it started running
    recognising_since: float = None
    cancelling: bool = False
    segments: list = field(default_factory=list)
    speech_seconds: float = None
    result: Transcript = None
    written: dict = field(default_factory=dict)   # format -> Path
    error: str = ""
    elapsed: float = 0.0
    formats: list = field(default_factory=list)  # formats asked for when it started
    saved_as: str = None         # its entry in the history, once remembered
    saved_at: float = 0.0        # when it was first remembered (keeps its place in the list)
    model: str = ""              # model key ("RNNT", "Whisper") that recognises or recognised it
    edits: int = 0               # how many times its text was changed in the window (plan 03, 06)
    speaker_error: str = ""      # why the last speaker search failed (plan 07), shown under the text


class Controller:
    """The window's state. Page calls arrive on bridge threads, worker events on
    the event thread; one lock keeps them in order."""

    def __init__(self, worker, events, send, clock=time.perf_counter, probe=probe_duration,
                 desktop=None, settings_path=None, initial_files=(), history=None, sound_check=has_sound):
        self.worker = worker
        self.events = events
        self.send = send
        self.clock = clock
        self.probe = probe
        self.sound_check = sound_check   # path -> bool; files without sound are not added
        self.open_path = desktop.open_path if desktop else open_path
        self.show_in_folder = desktop.show_in_folder if desktop else show_in_folder
        self.settings_path = settings_path
        self.initial_files = list(initial_files)
        self.history = history       # gigaam_app.history.History, or None to remember nothing
        self.lock = threading.RLock()
        self.seq = 0
        self.ready_called = False
        self.files = []
        self.ids = itertools.count(1)
        self.running = None          # the QueuedFile on the worker, if any
        self.downloading = None      # model key being downloaded
        self.download_started = None
        self.asking = None           # model key the download question is open for
        self.declined = set()        # models the user said "not now" to
        self.loaded_key = None
        self.failed_load = None      # model whose load failed; its "error" event follows
        self.reread_ids = itertools.count(1)
        self.rereading = None        # the selected part being recognised again (dict), if any
        # Suggested fixes (plan 06): files whose doubtful words wait to be read again by the
        # other models, and the search that runs (one group of words on the worker at a time).
        self.suggest_queue = []      # file ids
        self.suggesting = None       # dict, see _pump_suggestions
        self.suggest_ids = itertools.count(1)
        # Speaker labels (plan 07): files waiting for a speaker search, the search on the worker
        # (one whole file, so no file is started meanwhile), and the speaker models' download,
        # made the first time speakers are looked for.
        self.speaker_queue = []      # {"id", "transcript", "count" (None: find the number)}
        self.diarizing = None        # dict, see _pump_speakers
        self.diarize_ids = itertools.count(1)
        self.speaker_download = None  # {"done", "total"} bytes while the speaker models download
        self.engine = {"state": "idle", "text": "Запуск...", "detail": ""}
        self.engine_before = dict(self.engine)  # the status line before a download (faster-whisper)
        # The player (plan 05): files reach the page through a local server; formats the
        # page cannot play get a temporary copy, made once per file.
        self.audio_server = AudioServer()
        self.audio_dir = None        # folder of the temporary copies, made on first need
        self.audio_copies = {}       # source Path -> playable copy Path
        self.audio_jobs = {}         # source Path -> running ffmpeg process
        self.probe_jobs = queue.Queue()
        self.startup_error = ""
        try:
            self.settings = config.load(settings_path)
        except (OSError, ValueError) as error:
            self.settings = config.Settings()
            self.startup_error = f"Файл настроек не прочитан, используются значения по умолчанию: {error}"
        self._restore()

    def start(self):
        self.event_thread = threading.Thread(target=self._event_loop, name="gigaam-events", daemon=True)
        self.event_thread.start()
        threading.Thread(target=self._probe_loop, name="gigaam-probe", daemon=True).start()

    def stop(self, timeout=10):
        """After the worker has stopped: handle its last events (a cancelled file's result
        is remembered for the next session), then end the event thread."""
        self.events.put(None)
        self.event_thread.join(timeout)

    # ------------------------------------------------------------------ messages

    def _emit(self, kind, data):
        """Send one change to the page. Before the page asked for its snapshot
        nothing is sent: the snapshot already holds the change."""
        if not self.ready_called:
            return
        self.seq += 1
        self.send({"seq": self.seq, "kind": kind, "data": data})

    def _emit_files(self):
        self._emit("files", [self._file_view(item) for item in self.files])

    def _emit_file(self, item):
        self._emit("file", self._file_view(item))

    def _set_engine(self, state, text, detail=""):
        self.engine = {"state": state, "text": text, "detail": detail}
        self._emit("engine", dict(self.engine))

    def _error(self, text, source=""):
        """A banner over the right pane. source "engine" banners close once a model loads."""
        self._emit("error", {"text": text, "source": source})

    def _notice(self, text):
        self._emit("notice", {"text": text})

    # ------------------------------------------------------------------ views

    def _file_view(self, item):
        """What the page needs to draw one file."""
        outputs = []
        if item.result is not None and item.result.segments:
            outputs = [{"format": fmt, "short": short, "label": label,
                        "path": str(item.written[fmt]) if fmt in item.written else None}
                       for fmt, short, label in OUTPUT_CHIPS]
        return {
            "id": item.id, "name": item.path.name, "path": str(item.path), "state": item.state,
            "detail": self._detail(item), "status": self._status(item), "model": self._model_name(item),
            "progress": item.progress, "segments": len(item.segments), "outputs": outputs,
            "duration": item.duration,
            "cancelling": item.cancelling, "can_cancel": item.state == RUNNING and not item.cancelling,
            "can_retry": item.state in (DONE, CANCELLED, FAILED), "can_remove": item.state != RUNNING,
            "suggest": self._suggest_view(item),
            "speakers": self._speakers_view(item),
        }

    def _model_name(self, item):
        """Full name of the model that recognises or recognised the file ("GigaAM v3 RNNT",
        "Whisper large-v3-turbo (q5_0)"); empty while it waits or when it is unknown."""
        if item.state not in (RUNNING, DONE, CANCELLED) or not item.model:
            return ""
        return catalog.model_title(item.model)

    def _detail(self, item):
        """The short line under the name in the list; a finished file also names its model."""
        length = duration_text(item.duration) + " - " if item.duration else ""
        model = f", {item.model}" if item.model else ""
        if item.state == WAITING:
            return length + "в очереди"
        if item.state == DONE:
            return length + ("готово" if item.segments else "речь не найдена") + model
        if item.state == CANCELLED:
            return length + "отменено" + model
        if item.state == FAILED:
            return "ошибка"
        return length + f"{item.progress * 100:.0f}%"

    def _status(self, item):
        """The line under the title on the right."""
        if item.state == WAITING:
            model = self.settings.model
            if self._blocked_model() == model and self.running is None:
                return f"Ждёт модель {model}: она ещё не скачана. Скачайте её в настройках или выберите другую."
            if self.running:
                return "В очереди. Распознавание начнётся после текущего файла."
            if self.diarizing is not None or self.speaker_download is not None:
                return "В очереди. Распознавание начнётся, когда закончится определение говорящих."
            return "В очереди."
        if item.state == RUNNING:
            if item.cancelling:
                return "Отмена... готовые фрагменты будут сохранены."
            if item.progress <= 0 or item.duration is None:
                return item.phase or "Подготовка..."
            text = f"Распознаю: {duration_text(item.progress * item.duration)} из {duration_text(item.duration)}"
            if 0.03 < item.progress < 1 and item.recognising_since is not None:
                spent = self.clock() - item.recognising_since
                text += ", осталось " + about_text(spent / item.progress * (1 - item.progress))
            return text
        if item.state == FAILED:
            return "Ошибка: " + item.error
        result = item.result
        length = duration_text(result.audio_seconds) if result else ""
        if item.state == CANCELLED:
            if not item.segments:
                return "Отменено до первого фрагмента, файлы не созданы."
            done = item.segments[-1].end
            return f"Отменено на {duration_text(done)} из {length}, готовые фрагменты сохранены."
        if not item.segments:
            return f"{length} - речь не найдена, файлы не созданы."
        parts = [length]
        if item.speech_seconds is not None:
            parts.append(f"речь {duration_text(item.speech_seconds)}")
        speed = int(result.audio_seconds / item.elapsed) if item.elapsed > 0 else 0
        finished = f"готово за {duration_text(item.elapsed) if item.elapsed >= 60 else f'{item.elapsed:.0f} с'}"
        if speed >= 2:
            finished += f", {times_text(speed)} быстрее записи"
        parts.append(finished)
        return " - ".join(parts)

    def _options(self):
        models = []
        for key in MODELS:
            info = catalog.find(key)
            note = MODEL_NOTES.get(key, info.description)
            installed = True
            if not info.bundled:
                installed = catalog.installed_folder(info) is not None
                note += " Скачана." if installed else f" Скачивается отдельно, {size_text(info.download_size)}."
            models.append({"key": key, "title": key, "note": note, "language": info.model_type == "whisper",
                           "installed": installed})
        languages = [{"key": code, "label": name} for code, name in LANGUAGES]
        if self.settings.language not in dict(LANGUAGES):
            languages.append({"key": self.settings.language, "label": self.settings.language})
        return {
            "models": models,
            "languages": languages,
            "devices": [{"key": key, "label": label} for key, label in DEVICES],
            "formats": [{"key": fmt, "label": FORMAT_LABELS[fmt]} for fmt in FORMATS],
            "cpu_count": os.cpu_count() or 8,
            "max_speakers": MAX_SPEAKERS,
            "speaker_download": size_text(catalog.SPEAKER_MODEL.download_size),
            "whisper_cpu": self._whisper_cpu_options(),
            "speech_defaults": self._speech_view(config.Settings()),
            "speech_limits": {key: list(limits) for key, limits in SPEECH_LIMITS.items()},
            "config_note": f"Остальные параметры поиска речи задаются в файле "
                           f"{self.settings_path or config.default_path()}.",
        }

    def _whisper_cpu_options(self):
        """The two cards of "Whisper на процессоре" (plan 08 C2): key, title, note. The choice
        covers the search and, since C5, the main text when Whisper is the chosen model."""
        info = catalog.FAST_WHISPER_MODEL
        installed = self._model_installed(info.key)
        fast_note = "Быстрее на процессоре: текст в 1,4 раза, поиск вариантов в 1,6-2 раза. " + (
            "Скачана." if installed else f"Скачивается отдельно, {size_text(info.download_size)}.")
        return [{"key": "whisper.cpp", "title": "whisper.cpp", "note": "Входит в программу вместе с Whisper."},
                {"key": "faster-whisper", "title": "faster-whisper (int8)", "note": fast_note,
                 "installed": installed}]

    @staticmethod
    def _speech_view(settings):
        """The speech search settings the window shows (plan 07 H2)."""
        return {key: getattr(settings.vad, key) for key in SPEECH_LIMITS}

    def _settings_view(self):
        s = self.settings
        return {"model": s.model, "language": s.language, "device": s.device, "cpu_threads": s.cpu_threads,
                "outputs": list(s.outputs), "include_timestamps": s.include_timestamps,
                "terms": s.terms, "doubt_marks": s.doubt_marks, "doubt_style": s.doubt_style,
                "doubt_light": s.doubt_light, "doubt_strong": s.doubt_strong, "player_volume": s.player_volume,
                "suggest": s.suggest, "whisper_cpu": s.whisper_cpu, "speakers": s.speakers,
                "show_speakers": s.show_speakers, **self._speech_view(s)}

    # ------------------------------------------------------------------ page calls

    def ready(self):
        """The page is drawn: return everything it shows, then start the model."""
        with self.lock:
            first = not self.ready_called
            if first:
                for path in self.initial_files:
                    self._add(Path(path))
            snapshot = {"seq": self.seq, "files": [self._file_view(item) for item in self.files],
                        "engine": dict(self.engine), "settings": self._settings_view(), "options": self._options()}
            self.ready_called = True
            if first:
                if self.startup_error:
                    self._error(self.startup_error)
                self._request_load()
                self._pump()
            return snapshot

    def add_files(self, paths):
        """Add files (or the media files directly inside dropped folders). Files without
        sound are not added; one notice names them. Returns how many were added."""
        candidates = []      # (path, needs the sound check): folder contents pass by extension
        missing = []
        empty_folders = []
        for raw in paths or []:
            if not raw:
                continue
            path = Path(str(raw).strip().strip('"'))
            if path.is_dir():
                children = [child for child in sorted(path.iterdir())
                            if child.is_file() and child.suffix.lower() in MEDIA_SUFFIXES]
                candidates.extend((child, False) for child in children)
                if not children:
                    empty_folders.append(path.name)
            elif path.is_file():
                candidates.append((path, True))
            else:
                missing.append(path)
        # The sound check runs ffmpeg once per file, outside the lock and several at a time,
        # so a big drop does not hold up the window's other calls.
        to_check = [path for path, check in candidates if check]
        with ThreadPoolExecutor(max_workers=8) as pool:
            sound = dict(zip(to_check, pool.map(self.sound_check, to_check)))
        refused = [path.name for path in to_check if not sound[path]]

        # The page shows one toast at a time, so all the notes go into one notice.
        notes = [f"Файл не найден: {path}" for path in missing]
        if refused:
            notes.append(refused_text(refused))
        notes.extend(f"В папке нет аудио и видео: {name}" for name in empty_folders)

        added = 0
        with self.lock:
            first = len(self.files)
            for path, check in candidates:
                if not check or sound[path]:
                    added += self._add(path)
            if notes:
                self._notice(". ".join(notes))
            if added:
                self.declined.discard(self.settings.model)
                self._pump()
                self._emit_files()
                # Plan 07 H3: the page shows the first added file at once, also when it waits.
                self._emit("added", {"id": self.files[first].id})
        return added

    def _add(self, path):
        path = path.resolve()
        if any(item.path == path and item.state in (WAITING, RUNNING) for item in self.files):
            return 0
        item = QueuedFile(id=str(next(self.ids)), path=path)
        self.files.append(item)
        self.probe_jobs.put(item)
        return 1

    def remove(self, file_id):
        with self.lock:
            item = self._find(file_id)
            if item is None or item.state == RUNNING:
                return False
            self.files.remove(item)
            self._forget(item)
            self._emit_files()
            return True

    def cancel(self, file_id):
        with self.lock:
            item = self._find(file_id)
            if item is None or item.state != RUNNING or item.cancelling:
                return False
            item.cancelling = True
            self.worker.cancel.set()
            self._emit_file(item)
            return True

    def retry(self, file_id):
        with self.lock:
            item = self._find(file_id)
            if item is None or item.state not in (DONE, CANCELLED, FAILED):
                return False
            fresh = QueuedFile(id=item.id, path=item.path, duration=item.duration,
                               saved_as=item.saved_as, saved_at=item.saved_at)
            self.files[self.files.index(item)] = fresh
            self.declined.discard(self.settings.model)
            self._emit("lines_reset", {"id": item.id})
            self._emit_file(fresh)
            self._pump()
            return True

    def segments(self, file_id):
        with self.lock:
            item = self._find(file_id)
            if item is None:
                return []
            return [self._segment_view(index, segment) for index, segment in enumerate(item.segments)]

    @staticmethod
    def _segment_view(index, segment):
        """One line of text for the page, with its words, so a selection maps to word times.
        A word is [start, end, text, confidence, suggestions, speaker]; confidence is None when
        not known, suggestions None or the offers kept on the word (Word.suggestions, plan 06),
        speaker None or an index into the file's speaker names (plan 07)."""
        return {"index": index, "start": segment.start, "end": segment.end, "text": segment.text,
                "words": [[word.start, word.end, word.text, word.confidence, word.suggestions, word.speaker]
                          for word in segment.words]}

    def copy_text(self, file_id, with_times, for_llm=False, with_speakers=True):
        """The text as in the saved files: plain, or with [start - end] timecodes, or for
        an LLM (doubtful words marked, below the dotted threshold of the settings).
        with_speakers: False leaves the speaker names out, as the window shows them hidden
        (the saved files always carry them, owner 2026-11-09)."""
        with self.lock:
            item = self._find(file_id)
            if item is None:
                return ""
            model = item.result.model if item.result is not None else (item.model or "")
            speakers = list(item.result.speakers) if item.result is not None and item.result.speakers else None
            if not with_speakers:
                speakers = None
            transcript = Transcript(source=str(item.path), model=model, device="", segments=list(item.segments),
                                    speakers=speakers)
            doubt_below = self.settings.doubt_light
        if for_llm:
            return llm_text(transcript, doubt_below)
        return timestamped_text(transcript) if with_times else plain_text(transcript)

    def open_output(self, file_id, fmt):
        with self.lock:
            item = self._find(file_id)
            path = item.written.get(fmt) if item else None
        if path is None:
            return False
        if not path.is_file():
            self._notice_locked(f"Файл не найден: {path}")
            return False
        self.open_path(path)
        return True

    def create_output(self, file_id, fmt):
        """Write one more format for a finished file from the text already recognised."""
        with self.lock:
            item = self._find(file_id)
            if item is None or item.result is None or not item.result.segments or fmt not in FORMATS:
                return False
            result = item.result
            doubt_below = self.settings.doubt_light
        try:
            written = write_outputs(result, [fmt], doubt_below=doubt_below)
        except (OSError, ValueError) as error:
            with self.lock:
                self._error(f"Не удалось сохранить {FORMAT_LABELS[fmt]}: {error}")
            return False
        with self.lock:
            item.written[fmt] = written[0]
            self._remember(item)
            self._emit_file(item)
        return True

    # ------------------------------------------------------------------ fixing a selected part (plan 03)

    def _fixable(self, file_id, first=None, last=None):
        """The file whose text may be fixed (finished or cancelled with text, not running),
        with the selection checked; ValueError otherwise."""
        item = self._find(file_id)
        if item is None or item.state not in (DONE, CANCELLED) or item.result is None or not item.segments:
            raise ValueError("Этот текст сейчас нельзя исправить")
        if first is not None:
            fix.check_selection(item.segments, tuple(first), tuple(last))
        return item

    def audio(self, file_id, convert=False):
        """Where the page's player gets a file's sound (plan 05 A2):
        {"id", "url", "preparing"}. The original file when its format plays in the window,
        else (or with convert, after the original failed to play) a temporary copy; while
        that copy is being made, url is None and an "audio_ready" message follows."""
        with self.lock:
            item = self._find(file_id)
            if item is None or not Path(item.path).is_file():
                return None
            path = Path(item.path)
            if not convert and path.suffix.lower() in audio_module.PLAYABLE_SUFFIXES:
                return {"id": item.id, "url": self.audio_server.register(path), "preparing": False}
            if path in self.audio_copies:
                return {"id": item.id, "url": self.audio_server.register(self.audio_copies[path]),
                        "preparing": False}
            if path not in self.audio_jobs:
                if self.audio_dir is None:
                    self.audio_dir = Path(tempfile.mkdtemp(prefix="gigaam-audio-"))
                self.audio_jobs[path] = None  # taken; the process starts on the thread
                threading.Thread(target=self._make_playable, args=(item.id, path), daemon=True,
                                 name="gigaam-audio-copy").start()
            return {"id": item.id, "url": None, "preparing": True}

    def _make_playable(self, file_id, path):
        """Make the playable copy (Opus, or MP3 when this ffmpeg has no Opus) and tell the page."""
        error = "ffmpeg"
        for codec, suffix in (("libopus", ".opus"), ("libmp3lame", ".mp3")):
            target = self.audio_dir / f"{os.urandom(6).hex()}{suffix}"
            try:
                process = audio_module.start_playable_copy(path, target, codec)
            except (OSError, RuntimeError) as problem:
                error = str(problem)
                break
            with self.lock:
                if path not in self.audio_jobs:  # the window closed meanwhile
                    process.kill()
                    return
                self.audio_jobs[path] = process
            _, stderr = process.communicate()
            if process.returncode == 0 and target.is_file():
                with self.lock:
                    self.audio_jobs.pop(path, None)
                    self.audio_copies[path] = target
                    self._emit("audio_ready", {"id": file_id, "url": self.audio_server.register(target)})
                return
            lines = stderr.decode("utf-8", "replace").strip().splitlines()
            error = lines[-1] if lines else f"exit code {process.returncode}"
            with self.lock:
                if path not in self.audio_jobs:
                    return
        with self.lock:
            self.audio_jobs.pop(path, None)
            self._emit("audio_ready", {"id": file_id, "url": None})
            self._notice(f"Не удалось подготовить звук для проигрывания: {error}")

    def _close_audio(self):
        """The window is closing: stop copies being made, the server, delete the copies."""
        with self.lock:
            jobs = [process for process in self.audio_jobs.values() if process is not None]
            self.audio_jobs.clear()
            folder, self.audio_dir = self.audio_dir, None
        for process in jobs:
            process.kill()
            process.wait()
        self.audio_server.stop()
        if folder is not None:
            shutil.rmtree(folder, ignore_errors=True)

    def clip(self, file_id, first, last):
        """The selected words as a WAV to play: {"start", "end", "url"} (a data: URL)."""
        with self.lock:
            item = self._fixable(file_id, first, last)
            start, end = fix.play_range(item.segments, tuple(first), tuple(last), item.result.audio_seconds)
            path = item.path
        try:
            data = wav_clip(path, start, end - start)
        except (OSError, RuntimeError) as error:
            self._notice_locked(f"Не удалось вырезать звук: {error}")
            return None
        return {"start": start, "end": end, "url": "data:audio/wav;base64," + base64.b64encode(data).decode("ascii")}

    def reread(self, file_id, first, last, terms=""):
        """Recognise the selected words again with each available model (plan 03 A3).

        Returns what the page shows at once: the current text and the models that will
        answer; their readings follow as "reading" messages."""
        with self.lock:
            item = self._fixable(file_id, first, last)
            first, last = tuple(first), tuple(last)
            segments = item.segments
            if fix.word_at(segments, last).end - fix.word_at(segments, first).start > fix.MAX_SECONDS:
                raise ValueError(f"Выделите не больше {fix.MAX_SECONDS:.0f} секунд речи")
            # The piece holds a few words of context on each side (fix.py explains why).
            context_first, context_last = fix.context_bounds(segments, first, last)
            windows = fix.search_windows(segments, context_first, context_last, item.result.audio_seconds)
            context = fix.positions_between(segments, context_first, context_last)
            terms = " ".join(str(terms or "").split())[:config.MAX_TERMS_LENGTH]
            if terms != self.settings.terms:
                self.settings.terms = terms
                self._save_settings()
                self._emit("settings", self._settings_view())
            # The page knows Whisper by its key "Whisper"; the model process gets the engine that
            # reads it here (faster-whisper on the processor when chosen, plan 08 C5). A file
            # read on a video card with "Авто" keeps whisper.cpp under its own key, as the
            # search does: the same model under the other key would be a second copy on the card.
            whisper = "Whisper" if self._on_gpu(item) else self._whisper_engine()
            models = [key for key in REREAD_MODELS
                      if self._model_installed(key) or (key == "Whisper" and whisper != "Whisper")]
            engines = [whisper if key == "Whisper" else key for key in models]
            request = next(self.reread_ids)
            self.rereading = {"request": request, "id": item.id, "transcript": item.result, "first": first,
                           "last": last, "readings": {},
                           "context": [fix.word_at(segments, position) for position in context],
                           "selected": (context.index(first), context.index(last)),
                           "current": fix.selected_text(segments, first, last)}
            self.worker.jobs.put(("reread", request, item.path, windows, engines, self.settings.engine_device,
                                  self.settings.cpu_threads, self.settings.language, terms or None))
            return {"request": request, "current": self.rereading["current"],
                    "models": [{"key": key, "title": catalog.model_title(key)} for key in models],
                    "whisper_missing": "Whisper" not in models,
                    "waiting": self.running is not None or self.diarizing is not None}

    def apply_fix(self, file_id, first, last, text, model=None):
        """Put text in place of the selected words; the saved files and the history follow.

        model: the reading the text came from. Unchanged, its words keep their times;
        text typed or changed by hand gets times spread over the selected range."""
        with self.lock:
            item = self._fixable(file_id, first, last)
            first, last = tuple(first), tuple(last)
            reread = self.rereading
            same_selection = (reread is not None and reread["id"] == item.id and reread["transcript"] is item.result
                              and reread["first"] == first and reread["last"] == last)
            reading = reread["readings"].get(model) if same_selection and model else None
            if reading is not None and " ".join(word.text for word in reading) == " ".join(str(text).split()):
                words = list(reading)
            else:
                start, end = fix.play_range(item.segments, first, last, item.result.audio_seconds)
                words = fix.spread_words(str(text), start, end)
            if not words:
                raise ValueError("Пустой текст: чтобы убрать слова, оставьте хотя бы одно")
            fix.replace_words(item.segments, first, last, words)
            self._edited(item)
        self._write_again(item)
        return True

    def _edited(self, item):
        """The text of a file was changed in place (under the lock)."""
        item.result.segments = item.segments  # restored files keep a copy of the list
        item.edits += 1
        self.rereading = None

    def _write_llm_again(self, item):
        """The offers changed (found, or one left): write the file for an AI again, since it
        gives the other models' versions (outputs.llm_text). The other files do not show offers."""
        if "llm" not in item.written or item.result is None:
            return
        try:
            [path] = write_outputs(item.result, ["llm"], doubt_below=self.settings.doubt_light)
        except (OSError, ValueError) as problem:
            self._error(f"Не удалось перезаписать файл для ИИ: {problem}")
            return
        item.written["llm"] = path

    def _write_again(self, item, lines=True):
        """After the text or the speakers changed: write the saved files again, remember the
        file, redraw it (lines: its text too, else only the file, as after a speaker's rename)."""
        with self.lock:
            formats = list(item.written)
        error = None
        try:
            written = write_outputs(item.result, formats, doubt_below=self.settings.doubt_light) if formats else []
        except (OSError, ValueError) as problem:
            written, error = [], problem
        with self.lock:
            if error is None:
                item.written = dict(zip(formats, written))
            else:
                self._error(f"Текст исправлен, но файлы не перезаписаны: {error}")
            self._remember(item)
            if lines:
                self._emit("lines_changed", {"id": item.id})
            self._emit_file(item)

    def _reread_event(self, kind, request, *args):
        """Worker events of a selected part recognised again; old requests are ignored."""
        if self.rereading is None or self.rereading["request"] != request:
            return
        if kind in ("reread_loading", "reread_result") and args[0] == catalog.FAST_WHISPER_MODEL.key:
            args = ("Whisper",) + args[1:]  # the page and apply_fix know Whisper by this key
        data = {"request": request}
        if kind == "reread_range":
            data.update(phase="range", start=args[0], end=args[1])
        elif kind == "reread_loading":
            data.update(phase="loading", model=args[0])
        elif kind == "reread_result":
            model, words, error = args
            data.update(phase="result", model=model)
            if words is None:
                data["error"] = error
            else:
                words = fix.trim_reading(words, self.rereading["context"], *self.rereading["selected"])
                self.rereading["readings"][model] = words
                text = " ".join(word.text for word in words)
                data.update(text=text, same=fix.same_words(text, self.rereading["current"]))
        elif kind == "reread_failed":
            self._error("Не удалось распознать заново: " + args[0])
            return
        elif kind == "reread_done":
            data["phase"] = "done"
        self._emit("reading", data)

    # ------------------------------------------------------------------ suggested fixes (plan 06)

    def _own_model(self, item):
        return item.result.model if item.result is not None and item.result.model else item.model

    def _suggest_models(self, item):
        """The installed model that reads the doubtful words again: Whisper for GigaAM's text,
        GigaAM RNNT for Whisper's. Measured on the 455 s lecture (plan 06 A5, 2026-11-08):
        Whisper's offers were right in about half the places (the English terms), CTC's in 1
        of 11 (half-Latin words like "Lнt 4."), so CTC is not asked.
        Whisper on the processor is faster-whisper when Настройки choose it and it is
        downloaded (plan 08 C2); on a video card it stays whisper.cpp."""
        if self._own_model(item) == "Whisper":
            wanted = "RNNT"
        elif self._fast_search(item):
            wanted = catalog.FAST_WHISPER_MODEL.key
        else:
            wanted = "Whisper"
        return [wanted] if self._model_installed(wanted) else []

    def _fast_search(self, item):
        """True when faster-whisper reads the search's pieces: chosen in Настройки, downloaded,
        and Whisper runs on the processor (the device is "Процессор", or "Авто" and the file
        was recognised on the processor, so there is no video card for whisper.cpp either)."""
        return (self.settings.whisper_cpu == "faster-whisper"
                and self._model_installed(catalog.FAST_WHISPER_MODEL.key)
                and (self.settings.engine_device == "cpu"
                     or (self.settings.engine_device == "auto" and not self._on_gpu(item))))

    def _on_gpu(self, item):
        """True when the file was recognised on a video card, so Whisper most likely runs on one
        too (the same device setting); False on the CPU."""
        device = (item.result.device if item.result is not None else "") or ""
        return self.settings.engine_device != "cpu" and device.upper().startswith("GPU")

    def _suggest_by_itself(self, item):
        """Whether the search starts after the file without the button (Settings.suggest)."""
        mode = self.settings.suggest
        return mode == "always" or (mode == "gpu" and self._on_gpu(item))

    def _suggest_view(self, item):
        """The line about suggested fixes under a finished file, and whether the
        "Найти варианты" button is offered: {"text", "can_find", "busy", "can_cancel", "searched"}."""
        searched = item.result is not None and item.result.suggestions_searched
        if item.state not in (DONE, CANCELLED) or item.result is None or not item.segments:
            return {"text": "", "can_find": False, "busy": False, "can_cancel": False, "searched": False}
        words = [word for segment in item.segments for word in segment.words]
        doubtful = any(word.confidence is not None and word.confidence < self.settings.doubt_light for word in words)
        can_find = bool(self._suggest_models(item))
        search = self.suggesting
        if search is not None and search["id"] == item.id:
            if search.get("cancelled"):
                return {"text": "Останавливаю поиск вариантов...", "can_find": False, "busy": True,
                        "can_cancel": False, "searched": searched}
            text = f"Ищу варианты для сомнительных слов: {search['done']} из {search['total']}"
            if search.get("loading"):
                text += f" (загрузка {search['loading']}...)"
            return {"text": text, "can_find": False, "busy": True, "can_cancel": True, "searched": searched}
        if item.id in self.suggest_queue:
            return {"text": "Варианты для сомнительных слов: в очереди", "can_find": False, "busy": True,
                    "can_cancel": True, "searched": searched}
        places = sum(1 for word in words if word.suggestions)
        if places:
            text = f"Другие модели предлагают варианты: {places} {places_word(places)}"
        elif not can_find and doubtful and self._own_model(item) != "Whisper":
            text = "Варианты для сомнительных слов предлагает Whisper: его можно скачать в Настройках"
        elif searched and doubtful:
            text = "Другие модели не предлагают других вариантов"
        elif doubtful and self.settings.suggest == "gpu" and not self._on_gpu(item):
            text = "На процессоре варианты ищутся долго, поэтому только по кнопке:"
        else:
            text = ""  # not searched yet, or nothing doubtful
        return {"text": text, "can_find": can_find, "busy": False, "can_cancel": False, "searched": searched}

    def find_suggestions(self, file_id):
        """The "Найти варианты" button: read the file's doubtful words again with the other models."""
        with self.lock:
            item = self._fixable(file_id)
            if not self._suggest_models(item):
                raise ValueError("Варианты предлагает Whisper: скачайте его в Настройках"
                                 if self._own_model(item) != "Whisper" else "Нет модели GigaAM RNNT, чтобы сравнить")
            self._queue_suggestions(item)
            self._emit_file(item)
            self._pump()
            return True

    def cancel_suggestions(self, file_id):
        """Stop the suggestion search of a file, or take it out of the line (owner 2026-11-09:
        "maybe we should be able to cancel jobs? like this long one looking for variants").
        The line already on the worker is read to its end (a few seconds) and its offers are
        kept; the lines after it are dropped. The file does not count as searched, so
        "Найти варианты" stays offered."""
        with self.lock:
            item = self._find(file_id)
            if item is None:
                return False
            search = self.suggesting
            if search is not None and search["id"] == item.id:
                if search.get("cancelled"):
                    return False
                search["cancelled"] = True
                search["pieces"] = []
                search.pop("held", None)
                if search["request"] is None:
                    self._end_search(item, cancelled=True)
                    self._pump()
                else:
                    self._emit_file(item)
                return True
            if item.id not in self.suggest_queue:
                return False
            self.suggest_queue.remove(item.id)
            self._emit_file(item)
            return True

    def _queue_suggestions(self, item):
        search = self.suggesting
        busy = search is not None and search["id"] == item.id and search["transcript"] is item.result
        if not busy and item.id not in self.suggest_queue:
            self.suggest_queue.append(item.id)

    def _positions(self, item, search):
        """Word object -> position for the file's text, made again after each edit."""
        if search.get("edits") != item.edits or "positions" not in search:
            search["positions"] = {id(word): (segment_index, word_index)
                                   for segment_index, segment in enumerate(item.segments)
                                   for word_index, word in enumerate(segment.words)}
            search["edits"] = item.edits
        return search["positions"]

    def _locate(self, item, search, words):
        """The positions of words that must still stand next to each other in the text, or
        None when the text there was changed since (a fix taken meanwhile)."""
        start = self._positions(item, search).get(id(words[0]))
        if start is None:
            return None
        positions = fix.positions_from(item.segments, start, len(words))
        if len(positions) != len(words) or any(fix.word_at(item.segments, position) is not word
                                               for position, word in zip(positions, words)):
            return None
        return positions

    def _pump_suggestions(self):
        """Send the next line with doubtful words to the worker. Called only when no file waits
        to be recognised, so a new file waits for one line at most (about a second).

        A whole line (one VAD chunk, at most 25 s) is read at once: Whisper hears the full
        sentence, and each line costs one 30 s Whisper window however many groups it holds
        (plan 06 A5: fewer wrong offers and "Tools Calling" right, against 1.5 s of
        context per group). A longer line (an old transcript, longer chunks in Settings)
        is read group by group with the context of plan 03's reread.

        self.suggesting: {"id", "transcript" (the search ends if the file is recognised
        again), "pieces" (still to do: {"groups": word objects (first, last), "line": read
        the whole line}), "total" and "done" (groups), "models", "request" (the job on the
        worker, None between jobs), "parts" (the job's pieces, from _next_part: one, or up to
        8 for faster-whisper), "held" (a piece made ready that starts the next job), "loading",
        "cancelled" (cancel_suggestions: no more pieces)}."""
        while self.suggesting is None or self.suggesting["request"] is None:
            search = self.suggesting
            if search is None:
                if not self.suggest_queue:
                    return
                item = self._find(self.suggest_queue.pop(0))
                if item is None or item.result is None or not item.segments:
                    continue
                groups = fix.doubt_groups(item.segments, self.settings.doubt_light)
                search = self.suggesting = {"id": item.id, "transcript": item.result,
                                            "pieces": self._suggest_pieces(item.segments, groups),
                                            "total": len(groups), "done": 0, "request": None,
                                            "models": self._suggest_models(item)}
            item = self._find(search["id"])
            if item is None or item.result is not search["transcript"]:  # removed or recognised again
                self.suggesting = None
                continue
            if not (search["pieces"] or search.get("held")) or not search["models"]:
                self._end_search(item, cancelled=bool(search.get("cancelled")))
                continue
            first = self._next_part(item, search)
            if first is None:
                continue  # every group of those pieces changed meanwhile
            parts = [first]
            # faster-whisper reads up to BATCH_SIZE pieces at once (plan 08 C2). Only pieces
            # of one known language go together: the batch is told a single language, and a
            # piece whose language Whisper must detect is read on its own.
            if search["models"] == [catalog.FAST_WHISPER_MODEL.key] and first["language"] not in (None, "", "auto"):
                while len(parts) < faster_whisper_model.BATCH_SIZE:
                    part = self._next_part(item, search)
                    if part is None:
                        break
                    if part["language"] != first["language"]:
                        search["held"] = part  # it starts the next batch
                        break
                    parts.append(part)
            search["parts"] = parts
            search["request"] = next(self.suggest_ids)
            more = tuple((part["windows"], part["language"]) for part in parts[1:])
            self.worker.jobs.put(("suggest", search["request"], item.path, first["windows"], search["models"],
                                  self.settings.engine_device, self.settings.cpu_threads,
                                  first["language"], self.settings.terms or None, more))
            self._emit_file(item)

    def _next_part(self, item, search):
        """The next piece of the search, made ready to send: {"context" (its words),
        "selected" (each group's (first, last) index in context), "size" (groups), "windows",
        "language"}. Pieces whose groups all changed since (a fix taken meanwhile) are skipped
        and counted as done. None when no piece is left."""
        held = search.pop("held", None)
        if held is not None:
            return held
        segments = item.segments
        while search["pieces"]:
            piece = search["pieces"].pop(0)
            located = []
            for first_word, last_word in piece["groups"]:
                first_located = self._locate(item, search, [first_word])
                last_located = self._locate(item, search, [last_word])
                if first_located is not None and last_located is not None:  # else changed meanwhile
                    located.append((first_located[0], last_located[0]))
            line = located[0][0][0] if located else None
            located = [(first, last) for first, last in located if first[0] == last[0] == line]
            search["done"] += len(piece["groups"]) - len(located)
            if not located:
                continue
            if piece["line"]:
                context_first, context_last = (line, 0), (line, len(segments[line].words) - 1)
            else:
                context_first, context_last = fix.context_bounds(segments, *located[0])
            context = fix.positions_between(segments, context_first, context_last)
            words = [fix.word_at(segments, position) for position in context]
            return {"context": words,
                    "selected": [(context.index(first), context.index(last)) for first, last in located],
                    "size": len(located),
                    "windows": fix.search_windows(segments, context_first, context_last, item.result.audio_seconds),
                    "language": self._suggest_language(item, words)}
        return None

    def _suggest_language(self, item, words):
        """The language Whisper is told for one piece of the search (plan 08 C1).

        A language chosen in Настройки is used as it is. With "auto" (the default) the
        language comes from GigaAM's own text of the piece (fix.language_hint), which spares
        Whisper its detection pass on the CPU; owner 2026-11-11: "ok lets do that. unless
        configured otherwise in settings". Whisper's own text is read by RNNT, which needs no
        language, so it is passed on unchanged."""
        language = self.settings.language
        if language not in (None, "", "auto") or self._own_model(item) == "Whisper":
            return language
        return fix.language_hint(words) or language

    @staticmethod
    def _suggest_pieces(segments, groups):
        """Doubtful groups (positions) -> pieces to read: one per line, or one per group on a
        line longer than fix.MAX_SECONDS. Groups are kept as word objects, which survive edits."""
        pieces = []
        for first, last in groups:
            words = segments[first[0]].words
            whole = words[-1].end - words[0].start <= fix.MAX_SECONDS
            group = (fix.word_at(segments, first), fix.word_at(segments, last))
            if whole and pieces and pieces[-1]["line"] and pieces[-1]["index"] == first[0]:
                pieces[-1]["groups"].append(group)
            else:
                pieces.append({"groups": [group], "line": whole, "index": first[0]})
        return pieces

    def _end_search(self, item, error=None, cancelled=False):
        """The search of a file ended: searched, or cancelled (the offers found so far stay),
        or failed."""
        self.suggesting = None
        if error is None:
            if not cancelled:
                item.result.suggestions_searched = True
            self._write_llm_again(item)
            self._remember(item)
        else:
            self._notice(f"Не удалось найти варианты для {item.path.name}: {error}")
        self._emit_file(item)

    def _suggest_event(self, kind, request, *args):
        """Worker events of a group of doubtful words read again; old requests are ignored."""
        search = self.suggesting
        if search is None or search["request"] != request:
            return
        item = self._find(search["id"])
        current = item is not None and item.result is search["transcript"]
        if kind == "suggest_loading":
            search["loading"] = args[0]
        elif kind == "suggest_result":
            search["loading"] = None
            # A model that fails here just offers nothing. The last field, when present, is
            # the piece of a batch the reading is for (plan 08 C2); a single piece has none.
            model, words, _error, *rest = args
            part = search["parts"][rest[0] if rest else 0]
            # Offers read by faster-whisper are Whisper's, as for the reader of the window.
            label = "Whisper" if model == catalog.FAST_WHISPER_MODEL.key else model
            found = [fix.suggestion_from(words, part["context"], *selected) for selected in part["selected"]]
            found = [offer for offer in found if offer is not None] if words else []
            positions = self._locate(item, search, part["context"]) if found and current else None
            if positions is not None:
                changed = set()
                for index, count, new_words in found:
                    fix.add_suggestion(item.segments, positions[index], count, new_words, label)
                    changed.add(positions[index][0])
                for segment_index in sorted(changed):
                    self._emit("line", {"id": item.id,
                                        **self._segment_view(segment_index, item.segments[segment_index])})
        elif kind == "suggest_failed":
            search["request"] = None
            if current:
                self._end_search(item, error=args[0])
            else:
                self.suggesting = None
            self._pump()
            return
        elif kind == "suggest_done":
            search["request"] = None
            search["done"] += sum(part["size"] for part in search["parts"])
            if not current:  # removed or recognised again meanwhile
                self.suggesting = None
            elif search.get("cancelled"):  # ends now, even when a file waits to be recognised
                self._end_search(item, cancelled=True)
            self._pump()
        if current:
            self._emit_file(item)

    def take_suggestion(self, file_id, position, index):
        """Put an offered reading in place of the words it is for (in their time span)."""
        with self.lock:
            item = self._fixable(file_id)
            position = tuple(position)
            fix.check_selection(item.segments, position, position)
            offers = fix.word_at(item.segments, position).suggestions or []
            if not 0 <= index < len(offers):
                raise ValueError("Этот вариант уже недоступен")
            offer = offers[index]
            positions = fix.positions_from(item.segments, position, offer["count"])
            if len(positions) != offer["count"]:
                raise ValueError("Этот вариант уже недоступен")
            words = fix.suggestion_words(offer)
            for word in words:
                word.confidence = None  # the user chose it: not doubtful any more, like text typed by hand
            fix.replace_words(item.segments, position, positions[-1], words)
            self._edited(item)
        self._write_again(item)
        return True

    def leave_suggestion(self, file_id, position, index):
        """The user keeps the text as it is: forget one offered reading."""
        with self.lock:
            item = self._fixable(file_id)
            position = tuple(position)
            fix.check_selection(item.segments, position, position)
            if not 0 <= index < len(fix.word_at(item.segments, position).suggestions or []):
                return False
            fix.drop_suggestion(item.segments, position, index)
            self._write_llm_again(item)
            self._remember(item)
            self._emit("line", {"id": item.id, **self._segment_view(position[0], item.segments[position[0]])})
            self._emit_file(item)
            return True

    # ------------------------------------------------------------------ speaker labels (plan 07)

    def _speakers_view(self, item):
        """The speakers of a finished file: {"names" (Transcript.speakers, [] when not looked
        for), "list" (the speakers that have words, in order: {"index", "name", "share" (per
        cent of the speech time)}), "found" (the model's own count, a hint), "text" (how the
        search goes, how many were found, or why it failed), "can_find" (a search may start),
        "busy", "can_cancel", "error"}."""
        names = list(item.result.speakers or []) if item.result is not None else []
        found = item.result.speakers_found if item.result is not None else None
        view = {"names": names, "list": self._speaker_shares(item) if names else [], "found": found,
                "text": "", "can_find": False, "busy": False, "can_cancel": False, "error": False}
        if item.state not in (DONE, CANCELLED) or item.result is None or not item.segments:
            return view
        search = self.diarizing
        if search is not None and search["id"] == item.id and search["transcript"] is item.result:
            if search["cancelling"]:
                text = "Определение говорящих: отмена..."
            elif search["total"]:
                fraction = search["done"] / search["total"]
                text = f"Определяю говорящих: {fraction * 100:.0f}%"
                if search["since"] is not None and fraction < 1:
                    # Counted from the first progress report, so the model load is left out.
                    started, first = search["since"]
                    spent = self.clock() - started
                    if fraction - first > 0.05 and spent > 2:
                        text += ", осталось " + about_text(spent / (fraction - first) * (1 - fraction))
            elif search["loading"]:
                text = "Определяю говорящих: загрузка моделей..."
            else:
                text = "Определяю говорящих..."
            return {**view, "text": text, "busy": True, "can_cancel": not search["cancelling"]}
        queued = [entry for entry in self.speaker_queue if entry["id"] == item.id]
        if queued:
            text = "Определение говорящих: в очереди"
            if self.speaker_download is not None and self.speaker_queue[0] is queued[0]:
                download = self.speaker_download
                text = (f"Скачиваю модели для определения говорящих: {download['done'] / 1024 ** 2:.0f} "
                        f"из {download['total'] / 1024 ** 2:.0f} МБ")
            return {**view, "text": text, "busy": True, "can_cancel": self.speaker_download is None}
        if item.speaker_error:
            return {**view, "text": "Не удалось определить говорящих: " + item.speaker_error, "can_find": True,
                    "error": True}
        text = "Найдено: " + speakers_text(len(view["list"])) if names else ""
        return {**view, "text": text, "can_find": True}

    @staticmethod
    def _speaker_shares(item):
        """The speakers that have words, in order, with their share of the speech time (per
        cent, whole numbers; a speaker with words always gets at least 1)."""
        names = item.result.speakers or []
        seconds = {}
        for segment in item.segments:
            for word in segment.words:
                if word.speaker is not None and 0 <= word.speaker < len(names):
                    seconds[word.speaker] = seconds.get(word.speaker, 0.0) + max(word.end - word.start, 0.01)
        total = sum(seconds.values()) or 1.0
        return [{"index": index, "name": names[index], "share": max(1, round(100 * seconds[index] / total))}
                for index in sorted(seconds)]

    def find_speakers(self, file_id, count=None):
        """The "Определить говорящих" button: find who speaks when in a finished file.
        count: the number of speakers when the user knows it, None (or 0) to find it."""
        with self.lock:
            item = self._fixable(file_id)
            count = int(count) if count else None
            if count is not None and not 1 <= count <= MAX_SPEAKERS:
                raise ValueError(f"Число говорящих: от 1 до {MAX_SPEAKERS}")
            search = self.diarizing
            if search is not None and search["id"] == item.id and search["transcript"] is item.result:
                raise ValueError("Говорящие в этом файле уже определяются")
            self._queue_speakers(item, count)
            self._emit_file(item)
            self._pump()
            return True

    def _queue_speakers(self, item, count=None):
        """Put a file in line for a speaker search; a file already waiting gets the new count."""
        item.speaker_error = ""
        for entry in self.speaker_queue:
            if entry["id"] == item.id:
                entry.update(transcript=item.result, count=count)
                return
        self.speaker_queue.append({"id": item.id, "transcript": item.result, "count": count})

    def cancel_speakers(self, file_id):
        """Stop the speaker search of a file, or take it out of the line."""
        with self.lock:
            item = self._find(file_id)
            if item is None:
                return False
            search = self.diarizing
            if search is not None and search["id"] == item.id:
                if search["cancelling"]:
                    return False
                search["cancelling"] = True
                self.worker.cancel.set()
            else:
                before = len(self.speaker_queue)
                self.speaker_queue = [entry for entry in self.speaker_queue if entry["id"] != item.id]
                if len(self.speaker_queue) == before:
                    return False
            self._emit_file(item)
            return True

    def rename_speaker(self, file_id, index, name):
        """A new name for one speaker of a file; every paragraph and every saved file follows.
        An empty name gives the speaker back its number ("Говорящий 2")."""
        with self.lock:
            item = self._fixable(file_id)
            names = item.result.speakers
            if not names or not 0 <= int(index) < len(names):
                raise ValueError("Этого говорящего уже нет")
            index = int(index)
            name = " ".join(str(name or "").split())[:60] or diarize.default_name(index)
            if names[index] == name:
                return True
            names[index] = name
        self._write_again(item, lines=False)
        return True

    def set_words_speaker(self, file_id, first, last, speaker=None):
        """Give the words first..last ([line, word] positions) to another speaker: an index
        into the names, or None for a new speaker ("Говорящий N"; a number whose speaker has no
        words left is used again). Neighbouring turns of one speaker join by themselves, since
        the window and the files start a turn where the speaker changes. Files follow."""
        with self.lock:
            item = self._fixable(file_id, first, last)
            names = item.result.speakers
            if not names:
                raise ValueError("Говорящие в этом файле ещё не определены")
            if speaker is None:
                used = {entry["index"] for entry in self._speaker_shares(item)}
                speaker = next((index for index in range(len(names)) if index not in used), len(names))
                if speaker == len(names):
                    names.append("")
                names[speaker] = diarize.default_name(speaker)
            elif not 0 <= int(speaker) < len(names):
                raise ValueError("Этого говорящего уже нет")
            speaker = int(speaker)
            for position in fix.positions_between(item.segments, tuple(first), tuple(last)):
                fix.word_at(item.segments, position).speaker = speaker
            item.result.segments = item.segments  # restored files keep a copy of the list
        self._write_again(item)
        return True

    def merge_speakers(self, file_id, source, target):
        """Every word of speaker `source` goes to `target` (one person found as two). The
        source's number stays unused until a new speaker takes it."""
        with self.lock:
            item = self._fixable(file_id)
            names = item.result.speakers or []
            source, target = int(source), int(target)
            if source == target or not (0 <= source < len(names) and 0 <= target < len(names)):
                raise ValueError("Этого говорящего уже нет")
            moved = 0
            for segment in item.segments:
                for word in segment.words:
                    if word.speaker == source:
                        word.speaker = target
                        moved += 1
            if not moved:
                raise ValueError("Этого говорящего уже нет")
            item.result.segments = item.segments
        self._write_again(item)
        return True

    def _pump_speakers(self):
        """Start the next speaker search, or the speaker models' download it needs. Called when
        no file waits to be recognised and nothing else runs on the worker. True when the
        worker got a job.

        self.diarizing: {"id", "transcript" (the result the speakers are for; a file recognised
        again meanwhile ignores them), "request", "count", "done" and "total" (windows),
        "since" ((clock, fraction) at the first progress), "loading", "cancelling"}."""
        if self.diarizing is not None or self.speaker_download is not None:
            return True
        if self.suggesting is not None and self.suggesting["request"] is not None:
            return False  # one group of doubtful words on the worker: start after it
        while self.speaker_queue:
            entry = self.speaker_queue[0]
            item = self._find(entry["id"])
            if item is None or item.result is not entry["transcript"] or not item.segments:
                self.speaker_queue.pop(0)  # removed or recognised again meanwhile
                continue
            if catalog.installed_folder(catalog.SPEAKER_MODEL) is None:
                info = catalog.SPEAKER_MODEL
                self.speaker_download = {"done": 0, "total": info.download_size}
                self.worker.cancel.clear()
                self.worker.jobs.put(("download", info))
                self._emit_file(item)
                return True
            self.speaker_queue.pop(0)
            request = next(self.diarize_ids)
            self.diarizing = {"id": item.id, "transcript": item.result, "request": request,
                              "count": entry["count"], "done": 0, "total": 0, "since": None,
                              "loading": False, "cancelling": False}
            self.worker.cancel.clear()
            self.worker.jobs.put(("diarize", request, item.path, self.settings.engine_device,
                                  self.settings.cpu_threads, entry["count"]))
            self._emit_file(item)
            self._emit_files()  # waiting files now say they wait for the speakers
            return True
        return False

    def _diarize_event(self, kind, request, *args):
        """Worker events of a speaker search; old requests are ignored."""
        search = self.diarizing
        if search is None or search["request"] != request:
            return
        item = self._find(search["id"])
        current = item is not None and item.result is search["transcript"]
        if kind == "diarize_loading":
            search["loading"] = True
        elif kind == "diarize_progress":
            search["done"], search["total"] = args
            search["loading"] = False
            if search["since"] is None and search["total"]:
                search["since"] = (self.clock(), search["done"] / search["total"])
        elif kind == "diarize_found":
            search["found"] = args[0]
        elif kind == "diarize_result":
            turns, error = args
            self.diarizing = None
            if current and turns is not None:
                turns = [diarize.Turn(start, end, speaker) for start, end, speaker in turns]  # tuples from the worker
                item.result.speakers = diarize.assign_speakers(item.segments, turns, item.result.speakers)
                # The hint next to the count: with a number given, what the model would have
                # found by itself; otherwise the speakers it did find.
                found = search.get("found") if search.get("count") else None
                item.result.speakers_found = found or len(item.result.speakers)
                self._write_again(item)
            elif current and error:
                item.speaker_error = error
                self._notice(f"Не удалось определить говорящих в {item.path.name}: {error}")
            if current:
                self._emit_file(item)
            self._emit_files()
            self._pump()
            return
        if current:
            self._emit_file(item)

    def _speaker_download_progress(self, done, total):
        self.speaker_download = {"done": done, "total": total or catalog.SPEAKER_MODEL.download_size}
        if self.speaker_queue:
            item = self._find(self.speaker_queue[0]["id"])
            if item is not None:
                self._emit_file(item)

    def _speaker_download_done(self, folder):
        self.speaker_download = None
        if folder is None:  # stopped: the window is closing
            self.speaker_queue = []
            self._emit_files()
            return
        self._pump()

    def _speaker_download_failed(self, text):
        """The speaker models could not be downloaded: the files that waited for them say why."""
        self.speaker_download = None
        for entry in self.speaker_queue:
            item = self._find(entry["id"])
            if item is not None:
                item.speaker_error = f"модели не скачались ({text})"
        self.speaker_queue = []
        self._error(f"Не удалось скачать модели для определения говорящих: {text}")
        self._emit_files()
        self._pump()

    def show_folder(self, file_id):
        with self.lock:
            item = self._find(file_id)
            if item is None:
                return False
            target = next(iter(item.written.values()), item.path)
        self.show_in_folder(target)
        return True

    def set_settings(self, change):
        """Apply settings from the page at once; they count from the next file."""
        with self.lock:
            s = self.settings
            before = self._engine_key()
            if "model" in change:
                s.model = catalog.find(change["model"]).key
            if "language" in change:
                if change["language"] not in dict(LANGUAGES):
                    raise ValueError(f"Unknown language {change['language']!r}")
                s.language = change["language"]
            if "device" in change:
                if change["device"] not in dict(DEVICES):
                    raise ValueError(f"Unknown device {change['device']!r}")
                s.device = change["device"]
            if "cpu_threads" in change:
                s.cpu_threads = max(0, int(change["cpu_threads"]))
            if "outputs" in change:
                chosen = [fmt for fmt in FORMATS if fmt in change["outputs"]]
                s.outputs = chosen or ["txt"]
            if "include_timestamps" in change:
                s.include_timestamps = bool(change["include_timestamps"])
            if "doubt_marks" in change:
                s.doubt_marks = bool(change["doubt_marks"])
            if "suggest" in change:
                if change["suggest"] not in config.SUGGEST_MODES:
                    raise ValueError(f"Unknown suggest mode {change['suggest']!r}")
                s.suggest = change["suggest"]
            if "whisper_cpu" in change:
                self._choose_whisper_cpu(change["whisper_cpu"])
            if "speakers" in change:
                s.speakers = bool(change["speakers"])
            if "show_speakers" in change:
                s.show_speakers = bool(change["show_speakers"])
            if "doubt_style" in change:
                if change["doubt_style"] not in config.DOUBT_STYLES:
                    raise ValueError(f"Unknown doubt style {change['doubt_style']!r}")
                s.doubt_style = change["doubt_style"]
            if "player_volume" in change:
                s.player_volume = min(1.0, max(0.0, float(change["player_volume"])))
            for key, (low, high) in SPEECH_LIMITS.items():
                if key in change:
                    # Out of range is pulled into it; the page shows the value that was kept.
                    value = min(high, max(low, float(change[key])))
                    if key == "vad_min_silence_ms":
                        s.vad.vad_min_silence_ms = int(round(value))
                    elif key == "vad_threshold":
                        s.vad.vad_threshold = round(value, 2)
                    else:
                        s.vad.max_duration = s.vad.vad_max_speech_s = value
            if "doubt_light" in change or "doubt_strong" in change:
                light = float(change.get("doubt_light", s.doubt_light))
                strong = float(change.get("doubt_strong", s.doubt_strong))
                if not 0 < strong < light <= 1:
                    raise ValueError("Doubt thresholds: expected 0 < strong < light <= 1")
                s.doubt_light, s.doubt_strong = light, strong
            self._save_settings()
            self._emit("settings", self._settings_view())
            if self._engine_key() != before:
                if "model" in change:
                    self.declined.discard(s.model)
                self._request_load(ask="model" in change)
                self._pump()
                self._emit_files()  # the waiting text may name the model
            return True

    def reset_settings(self):
        """Back to the default model, device, threads, formats, text view and the speech search
        settings the window shows. The other speech search keys, which only the settings file
        holds, stay as they are."""
        defaults = config.Settings()
        return self.set_settings({"model": defaults.model, "device": defaults.device,
                                  "cpu_threads": defaults.cpu_threads, "outputs": list(defaults.outputs),
                                  "include_timestamps": defaults.include_timestamps,
                                  "doubt_marks": defaults.doubt_marks, "doubt_style": defaults.doubt_style,
                                  "suggest": defaults.suggest, "whisper_cpu": defaults.whisper_cpu,
                                  "speakers": defaults.speakers,
                                  "show_speakers": defaults.show_speakers,
                                  "doubt_light": defaults.doubt_light, "doubt_strong": defaults.doubt_strong,
                                  **self._speech_view(defaults)})

    def _save_settings(self):
        """Every change is kept for the next start (gigaam-config.json, also read by the CLI)."""
        path = self.settings_path or config.default_path()
        try:
            config.save(self.settings, path)
        except OSError as error:
            self._error(f"Не удалось сохранить настройки в {path}: {error}")

    def download(self):
        """The user agreed to download the model the question was about."""
        with self.lock:
            model = self.asking
            if model is None or self.downloading:
                return False
            self.asking = None
            self.downloading = model
            self.download_started = self.clock()
            self.worker.cancel.clear()
            self.worker.jobs.put(("download", model))
            self.engine_before = dict(self.engine)  # put back after a download of faster-whisper
            self._set_engine("busy", f"Скачивание модели {model}...")
            self._emit("download", {"phase": "progress", "model": model, "fraction": 0.0,
                                    "status": "Подключение..."})
            return True

    def decline_download(self):
        with self.lock:
            if self.asking:
                self.declined.add(self.asking)
                if self.asking == catalog.FAST_WHISPER_MODEL.key:
                    self._whisper_cpu_back()
                self.asking = None
                self._emit_files()
            return True

    def _choose_whisper_cpu(self, engine):
        """Настройки -> "Whisper на процессоре" (plan 08 C2, layout B chosen by the owner on
        2026-11-11). Choosing faster-whisper before it is downloaded asks the usual download
        question; "Не сейчас", a stopped or failed download set whisper.cpp again."""
        if engine not in config.WHISPER_CPU_ENGINES:
            raise ValueError(f"Unknown Whisper engine {engine!r}")
        key = catalog.FAST_WHISPER_MODEL.key
        if engine == "faster-whisper" and not self._model_installed(key):
            if self.downloading:
                raise ValueError(f"Сейчас скачивается модель {self.downloading}; "
                                 "выберите faster-whisper, когда она скачается")
            self.declined.discard(key)
            self.asking = None  # a question about the main model gives way to this one
            self._ask_download(key)
        self.settings.whisper_cpu = engine

    def _whisper_cpu_back(self):
        """faster-whisper is not on disk after all: Whisper on the processor is whisper.cpp again."""
        self.settings.whisper_cpu = "whisper.cpp"
        self._save_settings()
        self._emit("settings", self._settings_view())

    def cancel_download(self):
        with self.lock:
            if self.downloading:
                self.worker.cancel.set()
            return True

    def close_question(self):
        """What closing the window now would stop, as the question to ask; None when
        nothing runs, so the window may close without asking."""
        with self.lock:
            waiting = sum(1 for item in self.files if item.state == WAITING)
            parts = []
            if self.running is not None:
                parts.append(f"Идёт распознавание файла {self.running.path.name}. "
                             "Оно остановится; текст, распознанный до этого, сохранится.")
            if self.downloading:
                parts.append(f"Идёт скачивание модели {self.downloading}. "
                             "Скачанная часть останется, в следующий раз скачивание продолжится.")
            if self.diarizing is not None:
                item = self._find(self.diarizing["id"])
                name = item.path.name if item is not None else ""
                parts.append(f"Идёт определение говорящих в файле {name}. Оно остановится, "
                             "текст останется без говорящих.")
            if not parts:
                return None
            if waiting:
                parts.append(f"Файлов в очереди: {waiting}; они не будут распознаны.")
            return "\n\n".join(parts)

    def ask_close(self):
        """The user is closing the window. If that would stop something, send the
        question to the page and return True (the window stays open for now)."""
        with self.lock:
            question = self.close_question()
            if question:
                self._emit("confirm_close", {"text": question})
            return bool(question)

    def close(self):
        """The window is closing: stop whatever runs; partial text of a running file is saved."""
        self.worker.cancel.set()
        self._close_audio()

    # ------------------------------------------------------------------ history

    def _restore(self):
        """Put the files remembered from earlier sessions at the top of the list."""
        if self.history is None:
            return
        for entry in self.history.load():
            self.files.append(QueuedFile(
                id=str(next(self.ids)), path=entry.path, state=entry.state, duration=entry.duration,
                progress=1.0 if entry.state == DONE else 0.0, segments=list(entry.transcript.segments),
                speech_seconds=entry.speech_seconds, result=entry.transcript, written=dict(entry.written),
                elapsed=entry.elapsed, formats=list(entry.written), saved_as=entry.key, saved_at=entry.saved_at,
                model=entry.transcript.model))

    def _remember(self, item):
        """Save a finished file for the next sessions; a file that ended with nothing to show
        (failed, or cancelled before any text) is not kept."""
        if self.history is None:
            return
        keep = item.result is not None and (item.state == DONE or (item.state == CANCELLED and item.segments))
        if not keep:
            if item.state != FAILED:  # a failed retry keeps the earlier result on disk
                self._forget(item)
            return
        entry = Entry(key=item.saved_as or new_key(), path=item.path, state=item.state, transcript=item.result,
                      written=dict(item.written), duration=item.duration, elapsed=item.elapsed,
                      speech_seconds=item.speech_seconds, saved_at=item.saved_at)
        try:
            self.history.save(entry)
        except OSError as error:
            self._error(f"Не удалось запомнить файл для следующего запуска: {error}")
            return
        item.saved_as, item.saved_at = entry.key, entry.saved_at

    def _forget(self, item):
        if self.history is not None and item.saved_as:
            try:
                self.history.delete(item.saved_as)
            except OSError as error:
                self._error(f"Не удалось убрать файл из сохранённого списка: {error}")
                return
            item.saved_as = None

    # ------------------------------------------------------------------ queue

    def _find(self, file_id):
        return next((item for item in self.files if item.id == str(file_id)), None)

    def _notice_locked(self, text):
        with self.lock:
            self._notice(text)

    def _engine_key(self):
        """(model key, device, threads) the model process loads for the main text. Whisper
        is "faster-whisper" when Настройки choose it for the processor (plan 08 C5)."""
        s = self.settings
        model = self._whisper_engine() if s.model == "Whisper" else s.model
        return model, s.engine_device, s.cpu_threads

    def _whisper_engine(self):
        """The model key that reads Whisper's text for the main text and "Распознать снова"
        (plan 08 C5, owner 2026-11-11): "faster-whisper" when Настройки choose it, it is
        downloaded and the device is not "Видеокарта" (with "Авто" the model process still
        puts whisper.cpp on a Vulkan card, engine.Transcriber); else "Whisper" (whisper.cpp)."""
        fast = catalog.FAST_WHISPER_MODEL.key
        if (self.settings.whisper_cpu == "faster-whisper" and self.settings.engine_device != "gpu"
                and self._model_installed(fast)):
            return fast
        return "Whisper"

    def _model_installed(self, key):
        return catalog.installed_folder(catalog.find(key)) is not None

    def _blocked_model(self):
        """The chosen model when it is not on disk, else None."""
        model = self.settings.model
        return None if self._model_installed(model) else model

    def _request_load(self, ask=False):
        """Load the chosen model now, while nothing runs, so the next file starts at once."""
        if not self.ready_called:
            return
        model = self.settings.model
        if not self._model_installed(model):
            self._set_engine("missing", f"{model} - не скачана")
            if ask:
                self._ask_download(model)
            return
        if self.running is None and self.downloading is None and self._engine_key() != self.loaded_key:
            self.worker.jobs.put(("load", self._engine_key()))

    def _ask_download(self, model):
        if self.asking == model or self.downloading:
            return
        info = catalog.find(model)
        self.asking = model
        text = (f"Модель {model} не входит в программу и скачивается отдельно: {size_text(info.download_size)}.\n\n"
                f"{MODEL_NOTES.get(model, info.description)}\n\n"
                "Если скачивание прервётся, в следующий раз оно продолжится с того же места.")
        self._emit("download", {"phase": "ask", "model": model, "text": text, "folder": f"Папка: {downloads_dir()}"})

    def _pump(self):
        """Start the next waiting file if nothing runs; with no file to start, the speaker
        searches go first, then the suggested fixes (both run on the same worker)."""
        if not self.ready_called or self.running is not None or self.downloading is not None:
            return
        if self.diarizing is not None or self.speaker_download is not None:
            return  # a whole-file job on the worker; its end calls _pump again
        item = next((item for item in self.files if item.state == WAITING), None)
        if item is None:
            self._pump_background()
            return
        model = self.settings.model
        if not self._model_installed(model):
            if model not in self.declined:
                self._ask_download(model)
            self._emit_file(item)
            self._pump_background()
            return
        formats = list(self.settings.outputs) or ["txt"]
        item.state = RUNNING
        item.model = model
        item.started = self.clock()
        item.phase = "Подготовка..."
        item.formats = formats
        self.running = item
        self.worker.jobs.put(("transcribe", item.path, self._engine_key(), self.settings.vad, formats,
                              self.settings.language, self.settings.doubt_light))
        self._emit_file(item)

    def _pump_background(self):
        if not self._pump_speakers():
            self._pump_suggestions()

    # ------------------------------------------------------------------ worker events

    def _event_loop(self):
        while True:
            event = self.events.get()
            if event is None:
                return
            with self.lock:
                try:
                    self.handle(event)
                except Exception as error:  # a bug here must not stop the event thread
                    self._error(f"Внутренняя ошибка окна: {error!r}")

    def handle(self, event):
        kind, args = event[0], event[1:]
        item = self.running
        if kind == "loading":
            model = "Whisper (faster-whisper)" if args[0] == catalog.FAST_WHISPER_MODEL.key else args[0]
            self._set_engine("busy", f"Загрузка модели {model}...")
            if item:
                item.phase = f"Загрузка модели {model}..."
                self._emit_file(item)
        elif kind == "loaded":
            device, seconds, model = args
            self.loaded_key = self.worker.engine_key
            if model == catalog.FAST_WHISPER_MODEL.key:
                model = "Whisper"  # the device names the engine: "процессор, faster-whisper"
            self._set_engine("ready", f"{model} - {device_name(device)}", f"Загружена за {seconds:.1f} с")
        elif kind == "load_failed":
            self.loaded_key = None
            self.failed_load = args[0]
            self._set_engine("error", f"{args[0]} - не загрузилась", args[1])
        elif kind == "status" and item:
            item.phase = args[0]
            item.recognising_since = self.clock()
            self._emit_file(item)
        elif kind == "progress" and item:
            item.progress = args[1]
            self._emit_file(item)
        elif kind == "stats" and item:
            item.speech_seconds = args[0].speech_seconds
            if item.duration is None:
                item.duration = args[0].audio_seconds
        elif kind == "segment" and item:
            segment = args[0]
            item.segments.append(segment)
            self._emit("segment", {"id": item.id, **self._segment_view(len(item.segments) - 1, segment)})
        elif kind == "finished" and item:
            self._finish(item, *args)
        elif kind.startswith("reread_"):
            self._reread_event(kind, *args)
        elif kind.startswith("suggest_"):
            self._suggest_event(kind, *args)
        elif kind.startswith("diarize_"):
            self._diarize_event(kind, *args)
        elif kind == "download_progress":
            self._download_progress(*args)
        elif kind == "download_done":
            self._download_done(*args)
        elif kind == "error":
            self._worker_error(args[0])

    def _finish(self, item, result, written):
        item.elapsed = self.clock() - item.started
        item.cancelling = False
        item.result = result
        if result is not None:
            # The model process sends the result as a copy of the lines it sent one by one.
            # Keep one set of lines: offers and edits change them in place, and the history
            # and the files are written from the result.
            item.segments = result.segments
        if result is not None and result.model:
            item.model = result.model  # the model that really ran (the same key as at the start)
        if result is None or result.cancelled:
            item.state = CANCELLED
        else:
            item.state = DONE
            item.progress = 1.0
        if result is not None:
            item.duration = result.audio_seconds or item.duration
        # write_outputs returns the paths in the order of the formats it was given.
        item.written = dict(zip(item.formats, written))
        self.running = None
        if item.state == DONE and item.segments and self.settings.speakers:
            self._queue_speakers(item)
        if item.state == DONE and item.segments and self._suggest_by_itself(item) and self._suggest_models(item):
            self._queue_suggestions(item)
        self._remember(item)
        self._emit_file(item)
        self._pump()

    def _worker_error(self, text):
        if self.speaker_download is not None and not self.downloading and not self.running:
            self._speaker_download_failed(text)
        elif self.downloading:
            model, self.downloading = self.downloading, None
            self.declined.add(model)
            if model == catalog.FAST_WHISPER_MODEL.key:
                self._whisper_cpu_back()
                self._set_engine(**self.engine_before)
            else:
                self._set_engine("error", f"{model} - не скачана", text)
            self._emit("download", {"phase": "failed", "model": model, "text": ""})
            self._error(f"Не удалось скачать модель {model}: {text}")
        elif self.running:
            self.failed_load = None
            item, self.running = self.running, None
            item.state = FAILED
            item.error = text
            item.cancelling = False
            self._emit_file(item)
            self._pump()
        elif self.failed_load:
            model, self.failed_load = self.failed_load, None
            self._error(f"Не удалось загрузить модель {model}: {text}", source="engine")
        else:
            self._error("Ошибка: " + text)

    def _download_progress(self, model, done, total):
        if model == catalog.SPEAKER_MODEL.key:
            self._speaker_download_progress(done, total)
            return
        fraction = done / total if total else 0.0
        status = f"{done / 1024 ** 2:.0f} из {total / 1024 ** 2:.0f} МБ"
        elapsed = self.clock() - (self.download_started or self.clock())
        if 0.02 < fraction < 1 and elapsed > 3:
            # Resumed bytes count as done from the start, so the first seconds are skipped.
            status += ", осталось " + about_text(elapsed / fraction * (1 - fraction))
        self._emit("download", {"phase": "progress", "model": model, "fraction": fraction, "status": status})

    def _download_done(self, model, folder):
        if model == catalog.SPEAKER_MODEL.key:
            self._speaker_download_done(folder)
            return
        self.downloading = None
        fast = model == catalog.FAST_WHISPER_MODEL.key
        if fast:  # not the chosen model: its status line comes back
            self._set_engine(**self.engine_before)
        if folder is None:
            self.declined.add(model)
            if fast:
                self._whisper_cpu_back()
            else:
                self._set_engine("missing", f"{model} - не скачана")
            self._emit("download", {"phase": "cancelled", "model": model,
                                    "text": "Скачивание остановлено. В следующий раз оно продолжится с того же места."})
            self._emit_files()
            return
        self._emit("download", {"phase": "done", "model": model, "text": f"Модель {model} скачана"})
        self._emit("options", self._options())
        self._request_load()
        self._pump()

    # ------------------------------------------------------------------ durations

    def _probe_loop(self):
        while True:
            item = self.probe_jobs.get()
            if item is None:
                return
            seconds = self.probe(item.path)
            with self.lock:
                if seconds and item.duration is None and item in self.files:
                    item.duration = seconds
                    self._emit_file(item)
