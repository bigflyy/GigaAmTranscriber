"""Tk desktop window. All model work runs on one worker thread; the UI polls its events.

The model starts loading as soon as the window opens, while the user picks a
file, and stays loaded between files. Changing model, device or threads loads
it again before the next transcription. A model that is not bundled is
downloaded first, after the user agrees; the progress bar shows the download.
"""

import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__, catalog, config, download
from .engine import MODELS, Transcriber
from .paths import downloads_dir
from .outputs import clock
from .worker import Worker

DEVICE_LABELS = {"Auto": "Авто", "GPU": "GPU", "CPU": "CPU"}
FORMAT_LABELS = (("txt", "TXT"), ("timestamps", "TXT с таймкодами"), ("srt", "SRT (субтитры)"),
                 ("json", "JSON (слова и время)"))
# Russian notes shown before a download, by model key (catalog descriptions are English).
MODEL_NOTES = {}
MEDIA_TYPES = [("Аудио и видео", "*.wav *.mp3 *.m4a *.ogg *.opus *.flac *.aac *.wma *.mp4 *.mkv "
                                  "*.mov *.avi *.webm"), ("Все файлы", "*.*")]


def hms(seconds):
    seconds = int(round(seconds))
    return f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"


class App:
    def __init__(self, root, initial_file=None):
        self.root = root
        root.title(f"GigaAM - Расшифровка речи {__version__}")
        root.geometry("820x560")
        root.minsize(660, 460)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.events = queue.Queue()
        self.worker = Worker(self.events)
        self.worker.start()
        self.running = False
        self.downloading = False
        self.segments = []
        self.output_files = []
        self.asr_started = None
        self.run_started = None
        try:
            self.settings = config.load()
            settings_note = None
        except (OSError, ValueError) as error:
            self.settings = config.Settings()
            settings_note = f"Файл настроек не прочитан, используются значения по умолчанию: {error}"

        self.file = tk.StringVar(value=str(initial_file or ""))
        self.model = tk.StringVar(value=self.settings.model)
        self.device = tk.StringVar(value=DEVICE_LABELS[self.settings.device])
        self.threads = tk.StringVar(value=str(self.settings.cpu_threads))
        self.show_times = tk.BooleanVar(value=self.settings.include_timestamps)
        self.formats = {fmt: tk.BooleanVar(value=fmt in self.settings.outputs) for fmt, _ in FORMAT_LABELS}
        self.status = tk.StringVar(value="Запуск...")
        self.engine_state = tk.StringVar(value="")
        self.eta = tk.StringVar()
        self.stats = tk.StringVar()
        self.output_label = tk.StringVar(value="Результат сохраняется рядом с исходным файлом.")
        self._build()
        if settings_note:
            self.status.set(settings_note)
        # Load the model only once the window is on screen: opening the model
        # holds the interpreter for about two seconds, which would delay the window.
        root.after(150, self.first_load)
        root.after(100, self.poll)
        if initial_file:
            root.after(200, self.start)

    # ------------------------------------------------------------------ layout

    def _build(self):
        body = ttk.Frame(self.root, padding=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(5, weight=1)

        files = ttk.Frame(body)
        files.grid(row=0, column=0, sticky="ew")
        files.columnconfigure(0, weight=1)
        self.file_entry = ttk.Entry(files, textvariable=self.file)
        self.file_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.browse_button = ttk.Button(files, text="Выбрать файл...", command=self.browse)
        self.browse_button.grid(row=0, column=1)

        actions = ttk.Frame(body)
        actions.grid(row=1, column=0, sticky="ew", pady=10)
        self.start_button = ttk.Button(actions, text="Распознать", command=self.start)
        self.start_button.pack(side="left")
        self.cancel_button = ttk.Button(actions, text="Отмена", command=self.cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=8)
        self.settings_button = ttk.Button(actions, text="Настройки", command=self.toggle_settings)
        self.settings_button.pack(side="left")
        ttk.Checkbutton(actions, text="Таймкоды в просмотре", variable=self.show_times,
                        command=self.render_preview).pack(side="right")

        self.settings_frame = ttk.LabelFrame(body, text="Настройки", padding=10)
        self.settings_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        row = ttk.Frame(self.settings_frame)
        row.pack(fill="x")
        ttk.Label(row, text="Модель").pack(side="left")
        self.model_box = ttk.Combobox(row, textvariable=self.model, values=tuple(MODELS),
                                      state="readonly", width=18)
        self.model_box.pack(side="left", padx=(6, 16))
        ttk.Label(row, text="Устройство").pack(side="left")
        self.device_box = ttk.Combobox(row, textvariable=self.device, values=tuple(DEVICE_LABELS.values()),
                                       state="readonly", width=7)
        self.device_box.pack(side="left", padx=(6, 16))
        ttk.Label(row, text="Потоки CPU (0 = авто)").pack(side="left")
        self.threads_box = ttk.Spinbox(row, textvariable=self.threads, from_=0, to=os.cpu_count() or 8, width=4)
        self.threads_box.pack(side="left", padx=6)
        self.model_box.bind("<<ComboboxSelected>>", lambda event: self.request_load(ask=True))
        self.device_box.bind("<<ComboboxSelected>>", lambda event: self.request_load())
        self.threads_box.bind("<FocusOut>", lambda event: self.request_load())

        outputs = ttk.Frame(self.settings_frame)
        outputs.pack(fill="x", pady=(8, 0))
        ttk.Label(outputs, text="Сохранять:").pack(side="left")
        for fmt, label in FORMAT_LABELS:
            ttk.Checkbutton(outputs, text=label, variable=self.formats[fmt]).pack(side="left", padx=(6, 0))

        bottom = ttk.Frame(self.settings_frame)
        bottom.pack(fill="x", pady=(8, 0))
        ttk.Button(bottom, text="Сохранить как настройки по умолчанию", command=self.save_settings).pack(side="left")
        ttk.Label(bottom, text=f"Параметры поиска речи: {config.CONFIG_NAME} рядом с программой",
                  foreground="#666").pack(side="left", padx=12)
        self.settings_frame.grid_remove()

        progress = ttk.Frame(body)
        progress.grid(row=3, column=0, sticky="ew")
        self.bar = ttk.Progressbar(progress, mode="determinate", maximum=1000)
        self.bar.pack(fill="x")
        line = ttk.Frame(progress)
        line.pack(fill="x", pady=(4, 0))
        ttk.Label(line, textvariable=self.status).pack(side="left")
        ttk.Label(line, textvariable=self.engine_state, foreground="#666").pack(side="right")
        ttk.Label(progress, textvariable=self.eta).pack(anchor="w")
        ttk.Label(progress, textvariable=self.stats, foreground="#444").pack(anchor="w")

        preview = ttk.Frame(body)
        preview.grid(row=5, column=0, sticky="nsew", pady=(8, 0))
        preview.columnconfigure(0, weight=1)
        preview.rowconfigure(0, weight=1)
        self.text = tk.Text(preview, wrap="word", state="disabled", font=("Segoe UI", 10), undo=False)
        self.text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(preview, command=self.text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scroll.set)

        footer = ttk.Frame(body)
        footer.grid(row=6, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(footer, textvariable=self.output_label, wraplength=640).pack(side="left")
        self.open_button = ttk.Button(footer, text="Открыть папку", command=self.open_folder, state="disabled")
        self.open_button.pack(side="right")

    # ---------------------------------------------------------------- settings

    def engine_key(self):
        device = {label: key for key, label in DEVICE_LABELS.items()}[self.device.get()]
        try:
            threads = max(0, int(self.threads.get()))
        except ValueError:
            threads = 0
        return self.model.get(), device.lower(), threads

    def first_load(self):
        """Finish drawing the window, then load the model. While the model opens
        the window cannot redraw, so it must not be left half-painted."""
        self.root.update()
        self.request_load()

    def request_load(self, ask=False):
        if not self.running and self.model_ready(ask):
            self.worker.jobs.put(("load", self.engine_key()))

    def model_ready(self, ask):
        """True when the chosen model is on disk. Otherwise, if ask is set, offer
        to download it; the model loads when the download has finished."""
        info = catalog.find(self.model.get())
        if catalog.installed_folder(info) is not None:
            return True
        size = info.download_size / 1024 ** 2
        size_text = f"{size / 1024:.1f} ГБ" if size >= 1024 else f"{size:.0f} МБ"
        self.engine_state.set(f"Модель {info.key} не скачана")
        if not ask:
            self.status.set(f"Модель {info.key} скачивается отдельно ({size_text}). "
                            "Нажмите «Распознать», чтобы скачать её.")
            return False
        question = (f"Модель {info.key} не входит в программу и скачивается отдельно: {size_text}.\n\n"
                    f"{MODEL_NOTES.get(info.key, info.description)}\n\n"
                    f"Папка: {downloads_dir()}\n\n"
                    "Если скачивание прервётся, в следующий раз оно продолжится с того же места. "
                    "Скачать сейчас?")
        if messagebox.askyesno("Скачать модель", question, parent=self.root):
            self.begin_download(info)
        return False

    def begin_download(self, info):
        self.running = self.downloading = True
        self.bar["value"] = 0
        self.eta.set("")
        self.run_started = time.perf_counter()
        self.set_controls(running=True)
        self.status.set(f"Скачивание модели {info.key}...")
        self.worker.jobs.put(("download", info.key))

    def current_settings(self):
        model, device, threads = self.engine_key()
        formats = [fmt for fmt, _ in FORMAT_LABELS if self.formats[fmt].get()]
        return config.Settings(model=model, device={"auto": "Auto", "gpu": "GPU", "cpu": "CPU"}[device],
                               cpu_threads=threads, include_timestamps=self.show_times.get(),
                               outputs=formats or ["txt"], vad=self.settings.vad)

    def save_settings(self):
        try:
            config.save(self.current_settings())
        except OSError as error:
            messagebox.showerror("Настройки", f"Не удалось сохранить: {error}", parent=self.root)
            return
        self.status.set(f"Настройки сохранены: {config.default_path()}")

    def toggle_settings(self):
        if self.settings_frame.winfo_ismapped():
            self.settings_frame.grid_remove()
        else:
            self.settings_frame.grid()

    # ------------------------------------------------------------------ actions

    def browse(self):
        path = filedialog.askopenfilename(parent=self.root, title="Выберите аудио или видео",
                                          filetypes=MEDIA_TYPES)
        if path:
            self.file.set(path)

    def start(self):
        if self.running:
            return
        path = Path(self.file.get().strip().strip('"'))
        if not path.is_file():
            messagebox.showerror("Файл", "Выберите существующий аудио- или видеофайл.", parent=self.root)
            return
        if not self.model_ready(ask=True):
            return
        formats = [fmt for fmt, _ in FORMAT_LABELS if self.formats[fmt].get()] or ["txt"]
        self.running = True
        self.segments = []
        self.output_files = []
        self.render_preview()
        self.bar["value"] = 0
        self.eta.set("")
        self.stats.set("")
        self.output_label.set("Результат сохраняется рядом с исходным файлом.")
        self.open_button.state(["disabled"])
        self.run_started = time.perf_counter()
        self.asr_started = None
        self.set_controls(running=True)
        self.worker.jobs.put(("transcribe", path, self.engine_key(), self.settings.vad, formats))

    def cancel(self):
        if self.running:
            self.worker.cancel.set()
            self.status.set("Остановка скачивания..." if self.downloading else
                            "Отмена... готовые фрагменты будут сохранены.")

    def close(self):
        self.worker.cancel.set()
        self.root.destroy()

    def open_folder(self):
        if self.output_files:
            subprocess.Popen(["explorer", "/select,", str(self.output_files[0])])

    def set_controls(self, running):
        for widget in (self.start_button, self.browse_button, self.file_entry, self.model_box,
                       self.device_box, self.threads_box):
            widget.state(["disabled"] if running else ["!disabled"])
        for widget in (self.model_box, self.device_box):
            if not running:
                widget.state(["readonly"])
        self.cancel_button.state(["!disabled"] if running else ["disabled"])

    # ------------------------------------------------------------------ events

    def poll(self):
        try:
            while True:
                self.handle(self.events.get_nowait())
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def handle(self, event):
        kind = event[0]
        if kind == "status":
            self.status.set(event[1])
        elif kind == "loading":
            self.status.set(f"Загрузка модели {event[1]}...")
        elif kind == "load_failed":
            pass  # the "error" event that follows shows it
        elif kind == "loaded":
            _, device, seconds, model = event
            self.engine_state.set(f"{model} - {device}, загружена за {seconds:.1f} с")
            if not self.running:
                self.status.set("Готово. Выберите аудио- или видеофайл.")
        elif kind == "stats":
            t = event[1]
            skipped = max(0.0, t.audio_seconds - t.recognised_seconds)
            self.stats.set(f"Аудио {hms(t.audio_seconds)} - речь {hms(t.speech_seconds)} - "
                           f"пропущено без речи {hms(skipped)}")
        elif kind == "progress":
            self.on_progress(event[1], event[2])
        elif kind == "download_progress":
            self.on_download_progress(*event[1:])
        elif kind == "download_done":
            self.on_download_done(event[1], event[2])
        elif kind == "segment":
            self.segments.append(event[1])
            self.append_preview(event[1])
        elif kind == "finished":
            self.on_finished(event[1], event[2])
        elif kind == "error":
            self.running = self.downloading = False
            self.set_controls(running=False)
            self.status.set("Ошибка: " + event[1])
            self.eta.set("")
            messagebox.showerror("Ошибка", event[1], parent=self.root)

    def on_progress(self, searched, recognised):
        # Speech search and recognition overlap; the bar shows recognised audio.
        now = time.perf_counter()
        self.bar["value"] = 1000 * recognised
        self.status.set(f"Распознано {recognised * 100:.0f}% (поиск речи {searched * 100:.0f}%)")
        if 0.03 < recognised < 1:
            left = (now - self.run_started) / recognised * (1 - recognised)
            self.eta.set(f"Осталось примерно {hms(left)}")

    def on_download_progress(self, model, done, total):
        fraction = done / total if total else 0.0
        self.bar["value"] = 1000 * fraction
        self.status.set(f"Скачивание модели {model}: {done / 1024 ** 2:.0f} из {total / 1024 ** 2:.0f} МБ")
        elapsed = time.perf_counter() - self.run_started
        if 0.02 < fraction < 1 and elapsed > 3:
            # Resumed bytes count as done from the start, so the first seconds
            # are skipped before an estimate is shown.
            self.eta.set(f"Осталось примерно {hms(elapsed / fraction * (1 - fraction))}")

    def on_download_done(self, model, folder):
        self.running = self.downloading = False
        self.set_controls(running=False)
        self.eta.set("")
        if folder is None:
            self.status.set("Скачивание остановлено. В следующий раз оно продолжится с того же места.")
            return
        self.bar["value"] = 1000
        self.status.set(f"Модель {model} скачана.")
        self.request_load()

    def on_finished(self, result, written):
        self.running = False
        self.set_controls(running=False)
        self.eta.set("")
        elapsed = time.perf_counter() - self.run_started
        if result is None:
            self.status.set("Отменено.")
            return
        self.output_files = written
        if written:
            self.output_label.set("Сохранено: " + "; ".join(path.name for path in written))
            self.open_button.state(["!disabled"])
        else:
            self.output_label.set("Речь не найдена, файлы не созданы." if not result.cancelled else
                                  "Отменено до первого фрагмента, файлы не созданы.")
        state = "Отменено" if result.cancelled else "Готово"
        speed = result.audio_seconds / elapsed if elapsed else 0
        self.bar["value"] = 1000 if not result.cancelled else self.bar["value"]
        self.status.set(f"{state} за {hms(elapsed)} ({speed:.0f}x быстрее реального времени), "
                        f"фрагментов: {len(result.segments)}")

    # ------------------------------------------------------------------ preview

    def line(self, segment):
        if self.show_times.get():
            return f"[{clock(segment.start)} - {clock(segment.end)}] {segment.text}\n"
        return segment.text + "\n"

    def append_preview(self, segment):
        # Follow new text only if the reader is already at the end.
        following = self.text.yview()[1] >= 0.999
        self.text.configure(state="normal")
        self.text.insert("end", self.line(segment))
        self.text.configure(state="disabled")
        if following:
            self.text.see("end")

    def render_preview(self):
        top = self.text.yview()[0]
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("end", "".join(self.line(segment) for segment in self.segments))
        self.text.configure(state="disabled")
        self.text.yview_moveto(top)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if sys.platform == "win32":
        try:  # sharp text on high-DPI screens
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    root = tk.Tk()
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    App(root, initial_file=argv[0] if argv else None)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
