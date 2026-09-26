"""Minimal Tk interface; all model work runs outside the UI thread."""

from argparse import ArgumentTypeError
from pathlib import Path
import math
import os
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from transcribe import format_audio_stats, format_segments, positive_int, run_transcription
from gui_help import HELP, OVERVIEW, HoverHint
from app_config import SETTINGS, default_config_path, read_config, validate_config, write_config


class TranscriberApp:
    def __init__(self, root):
        self.root = root
        self.root.title("GigaAM — Расшифровка речи")
        self.root.geometry("760x480")
        self.root.minsize(640, 440)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.events = queue.Queue()
        self.running = False
        self.cancel_event = threading.Event()
        self.advanced_visible = False
        self.file = tk.StringVar()
        self.model = tk.StringVar(value="RNNT")
        self.device = tk.StringVar(value="Auto")
        self.cpu_threads = tk.StringVar(value="4")
        self.status = tk.StringVar(value="Выберите аудио- или видеофайл.")
        self.output = tk.StringVar(value="Текст будет сохранён рядом с исходным файлом.")
        self.include_timestamps = tk.BooleanVar(value=True)
        self.segments = []
        self.saved_output = None
        self.eta = tk.StringVar()
        self.audio_stats = tk.StringVar()
        self.progress_started_at = None
        self.run_started_at = None
        self.estimated_finish_at = None
        self.values = {name: tk.StringVar(value=str(default))
                       for name, _, _, default in SETTINGS}
        self.controls = []
        self.help_hints = []
        self.help_window = None

        body = ttk.Frame(root, padding=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(5, weight=1)
        ttk.Label(body, text="GigaAM — Расшифровка речи", font=("Segoe UI", 15, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 10))

        files = ttk.Frame(body)
        files.grid(row=1, column=0, sticky="ew")
        files.columnconfigure(0, weight=1)
        entry = ttk.Entry(files, textvariable=self.file)
        entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        browse = ttk.Button(files, text="Выбрать файл…", command=self.browse)
        browse.grid(row=0, column=1)
        self.controls.extend((entry, browse))

        actions = ttk.Frame(body)
        actions.grid(row=2, column=0, sticky="ew", pady=10)
        self.start_button = ttk.Button(actions, text="Распознать", command=self.start)
        self.start_button.pack(side="left")
        self.controls.append(self.start_button)
        self.cancel_button = ttk.Button(actions, text="Отмена", command=self.cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=(8, 0))
        self.advanced_button = ttk.Button(actions, text="Настройки >", command=self.toggle_advanced)
        self.advanced_button.pack(side="left", padx=8)
        ttk.Checkbutton(actions, text="Включить таймкоды", variable=self.include_timestamps,
                        command=self.timestamps_changed).pack(side="left", padx=8)

        self.advanced = ttk.LabelFrame(body, text="Advanced settings", padding=10)
        self.advanced.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        for column in (1, 3):
            self.advanced.columnconfigure(column, weight=1)
        self.setting_label("Model", "model", row=0, column=0, sticky="w")
        model = ttk.Combobox(self.advanced, textvariable=self.model, values=("RNNT", "CTC"),
                             state="readonly", width=12)
        model.grid(row=0, column=1, sticky="ew", padx=(8, 20), pady=3)
        self.add_help(model, "model")
        self.setting_label("Device", "device", row=0, column=2, sticky="w")
        device = ttk.Combobox(self.advanced, textvariable=self.device,
                              values=("Auto", "CPU", "CUDA"), state="readonly", width=12)
        device.grid(row=0, column=3, sticky="ew", padx=(8, 0), pady=3)
        self.add_help(device, "device")
        self.controls.extend((model, device))
        for index, (name, label, _, _) in enumerate(SETTINGS):
            row, pair = divmod(index, 2)
            column = pair * 2
            self.setting_label(label, name, row=row + 1, column=column, sticky="w", pady=3)
            field = ttk.Entry(self.advanced, textvariable=self.values[name], width=12)
            field.grid(row=row + 1, column=column + 1, sticky="ew", padx=(8, 20 if pair == 0 else 0), pady=3)
            self.add_help(field, name)
            self.controls.append(field)
        self.setting_label("GigaAM CPU threads", "cpu_threads", row=5, column=2, sticky="w", pady=3)
        threads = ttk.Spinbox(self.advanced, textvariable=self.cpu_threads,
                              from_=1, to=max(4, os.cpu_count() or 1), width=12)
        threads.grid(row=5, column=3, sticky="ew", padx=(8, 0), pady=3)
        self.add_help(threads, "cpu_threads")
        self.controls.append(threads)
        self.setting_label("Silero: 1 thread; window size: 512 samples (fixed)", "silero_runtime",
            row=6, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Label(self.advanced, text="Default model: RNNT. CTC downloads on first use.").grid(
            row=7, column=0, columnspan=4, sticky="w", pady=3)
        reset = ttk.Button(self.advanced, text="Reset defaults", command=self.reset_defaults)
        reset.grid(row=8, column=0, columnspan=2, sticky="w", pady=(5, 0))
        self.controls.append(reset)
        ttk.Button(self.advanced, text="Parameter help", command=self.show_help).grid(
            row=8, column=2, columnspan=2, sticky="w", pady=(5, 0))
        configs = ttk.Frame(self.advanced)
        configs.grid(row=9, column=0, columnspan=4, sticky="w", pady=(8, 0))
        for label, command in (("Import config…", self.import_config),
                               ("Export config…", self.export_config),
                               ("Save as default", self.save_default_config)):
            button = ttk.Button(configs, text=label, command=command)
            button.pack(side="left", padx=(0, 8))
            self.controls.append(button)
            self.add_help(button, "config")
        self.advanced.grid_remove()

        progress = ttk.Frame(body)
        progress.grid(row=4, column=0, sticky="ew", pady=(0, 10))
        self.bar = ttk.Progressbar(progress, mode="determinate", maximum=100)
        self.bar.pack(fill="x")
        ttk.Label(progress, textvariable=self.status, wraplength=700).pack(anchor="w", pady=(5, 0))
        ttk.Label(progress, textvariable=self.eta, wraplength=700).pack(anchor="w")
        stats_label = ttk.Label(progress, textvariable=self.audio_stats, wraplength=700)
        stats_label.pack(anchor="w")
        self.help_hints.append(HoverHint(stats_label, "Audio duration and VAD filtering",
            "Durations use HH:MM:SS and describe the entire file. Speech is the combined "
            "duration of Silero VAD speech regions, including configured speech padding. "
            "Non-speech means VAD did not identify speech; it may include noise or music. "
            "Recognition chunks can retain pauses between speech regions, so the amount "
            "actually skipped may differ from the non-speech duration. These figures "
            "describe planned audio coverage, not completed transcription, even after cancellation."))
        preview = ttk.Frame(body)
        preview.grid(row=5, column=0, sticky="nsew")
        preview.columnconfigure(0, weight=1)
        preview.rowconfigure(0, weight=1)
        self.text = tk.Text(preview, wrap="word", height=9, state="disabled", font=("Segoe UI", 10))
        self.text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(preview, command=self.text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scroll.set)
        ttk.Label(body, textvariable=self.output, wraplength=700).grid(row=6, column=0, sticky="w", pady=(8, 0))
        self.root.after(100, self.poll)
        self.load_config(default_config_path(), automatic=True)

    def current_config(self):
        return validate_config({"model": self.model.get(), "device": self.device.get(),
            "cpu_threads": positive_int(self.cpu_threads.get()),
            "include_timestamps": self.include_timestamps.get(), **self.settings()})

    def load_config(self, path, automatic=False):
        if self.running:
            return
        try:
            config = read_config(path)
        except FileNotFoundError:
            if automatic:
                return
            messagebox.showerror("Ошибка конфигурации", f"Файл не найден: {path}", parent=self.root)
            return
        except (OSError, ValueError) as exc:
            messagebox.showerror("Ошибка конфигурации", f"{path}\n{exc}\nНастройки не изменены.", parent=self.root)
            return
        self.model.set(config["model"])
        self.device.set(config["device"])
        self.cpu_threads.set(str(config["cpu_threads"]))
        for name, _, _, _ in SETTINGS:
            self.values[name].set(str(config[name]))
        self.include_timestamps.set(config["include_timestamps"])
        if self.timestamps_changed() is not False:
            self.status.set(f"Настройки загружены: {Path(path).name}")

    def import_config(self):
        if self.running:
            return
        path = filedialog.askopenfilename(parent=self.root, title="Импорт настроек",
                                          filetypes=[("JSON config", "*.json")])
        if path:
            self.load_config(Path(path))

    def save_config(self, path):
        if self.running:
            return
        try:
            write_config(path, self.current_config())
        except (OSError, ValueError, ArgumentTypeError) as exc:
            messagebox.showerror("Ошибка сохранения настроек", str(exc), parent=self.root)
            return
        self.status.set(f"Настройки сохранены: {path}")

    def save_default_config(self):
        self.save_config(default_config_path())

    def export_config(self):
        if self.running:
            return
        path = filedialog.asksaveasfilename(parent=self.root, title="Экспорт настроек",
            defaultextension=".json", initialfile="gigaam-config.json", filetypes=[("JSON config", "*.json")])
        if path:
            self.save_config(Path(path))

    def add_help(self, widget, key):
        self.help_hints.append(HoverHint(widget, *HELP[key]))

    def setting_label(self, text, key, **grid):
        label = ttk.Label(self.advanced, text=text + " (?)", cursor="hand2")
        label.grid(**grid)
        self.add_help(label, key)
        label.bind("<Button-1>", lambda _event: self.show_help(key), add="+")

    def show_help(self, key=None):
        for hint in self.help_hints:
            hint.hide()
        if self.help_window is not None and self.help_window.winfo_exists():
            self.help_window.destroy()
        window = self.help_window = tk.Toplevel(self.root)
        window.title("Advanced settings — Parameter help")
        window.geometry("760x650")
        window.minsize(540, 360)
        window.transient(self.root)
        window.bind("<Escape>", lambda _event: window.destroy())
        body = ttk.Frame(window, padding=12)
        body.pack(fill="both", expand=True)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        text = tk.Text(body, wrap="word", font=("Segoe UI", 10), padx=12, pady=10)
        text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(body, command=text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        text.configure(yscrollcommand=scroll.set)
        text.tag_configure("heading", font=("Segoe UI", 12, "bold"), spacing1=12, spacing3=6)
        entries = [(key, HELP[key])] if key else list(HELP.items())
        if key is None:
            text.insert("end", OVERVIEW + "\n\n")
        for _, (title, description) in entries:
            text.insert("end", title + "\n", "heading")
            text.insert("end", description + "\n\n")
        text.configure(state="disabled")
        ttk.Button(body, text="Close", command=window.destroy).grid(row=1, column=0, sticky="e", pady=(10, 0))
        text.focus_set()

    def browse(self):
        name = filedialog.askopenfilename(parent=self.root, title="Выберите аудио или видео")
        if name:
            self.file.set(name)

    def toggle_advanced(self):
        for hint in self.help_hints:
            hint.hide()
        self.advanced_visible = not self.advanced_visible
        if self.advanced_visible:
            self.advanced.grid()
            self.root.geometry("760x790")
            self.advanced_button.configure(text="Настройки v")
        else:
            self.advanced.grid_remove()
            self.root.geometry("760x480")
            self.advanced_button.configure(text="Настройки >")

    def reset_defaults(self):
        self.model.set("RNNT")
        self.device.set("Auto")
        self.cpu_threads.set("4")
        for name, _, _, default in SETTINGS:
            self.values[name].set(str(default))

    def settings(self):
        result = {}
        for name, label, kind, _ in SETTINGS:
            try:
                value = kind(self.values[name].get())
            except ValueError:
                raise ValueError(f"«{label}»: введите число") from None
            if not (0 <= value < float("inf")):
                raise ValueError(f"«{label}»: введите конечное неотрицательное число")
            if name == "vad_threshold" and not 0 < value <= 1:
                raise ValueError("VAD threshold должен быть больше 0 и не больше 1")
            if name in ("max_duration", "min_duration", "strict_limit_duration", "vad_max_speech_s") and value == 0:
                raise ValueError(f"«{label}»: значение должно быть больше 0")
            result[name] = value
        return result

    def set_text(self, value, preserve_view=False):
        top = self.text.index("@0,0") if preserve_view else "1.0"
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", value)
        self.text.configure(state="disabled")
        self.text.yview(top)

    def append_segment(self, segment):
        # Append without rebuilding existing text, moving the viewport or clearing selection.
        top = self.text.index("@0,0")
        self.text.configure(state="normal")
        self.text.insert("end-1c", format_segments([segment], self.include_timestamps.get()))
        self.text.configure(state="disabled")
        self.text.yview(top)

    def set_running(self, running):
        self.running = running
        self.cancel_button.configure(state="normal" if running else "disabled")
        if not running:
            self.estimated_finish_at = None
            self.eta.set("")
        for widget in self.controls:
            state = "disabled" if running else ("readonly" if isinstance(widget, ttk.Combobox) else "normal")
            widget.configure(state=state)

    def cancel(self):
        if self.running:
            self.cancel_event.set()
            self.cancel_button.configure(state="disabled")
            self.estimated_finish_at = None
            self.eta.set("")
            self.status.set("Остановка после текущего этапа… Полученный текст останется в окне.")

    def update_eta(self, done, total, completed_at):
        if done == 0:
            # Model loading and VAD are excluded from segment timing.
            self.progress_started_at = completed_at
            self.estimated_finish_at = None
        if done >= total:
            self.estimated_finish_at = None
            self.eta.set("Распознавание завершено. Сохранение…")
        elif done and self.progress_started_at is not None:
            seconds_per_segment = (completed_at - self.progress_started_at) / done
            self.estimated_finish_at = completed_at + seconds_per_segment * (total - done)
        else:
            self.eta.set("Оценка времени появится после первого фрагмента.")

    def refresh_eta(self):
        if not self.running or self.estimated_finish_at is None:
            return
        seconds = math.ceil(self.estimated_finish_at - time.monotonic())
        if seconds <= 0:
            self.eta.set("Уточняем оставшееся время…")
            return
        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)
        duration = f"{minutes:02d}:{seconds:02d}"
        if hours:
            duration = f"{hours:02d}:" + duration
        self.eta.set(f"Осталось примерно: {duration}")

    def render_segments(self):
        self.set_text(format_segments(self.segments, self.include_timestamps.get()), preserve_view=True)

    def show_elapsed(self):
        if self.run_started_at is not None:
            elapsed = max(0.0, time.monotonic() - self.run_started_at)
            minutes, seconds = divmod(round(elapsed, 1), 60)
            hours, minutes = divmod(int(minutes), 60)
            self.eta.set(f"Затрачено времени: {hours:02d}:{minutes:02d}:{seconds:04.1f}")

    def timestamps_changed(self):
        # Keep structured results intact; only the view and exported text change.
        self.render_segments()
        if self.saved_output is not None and not self.running:
            return self.save_transcript()

    def save_transcript(self):
        try:
            self.saved_output.write_text(
                format_segments(self.segments, self.include_timestamps.get()), encoding="utf-8")
        except OSError as exc:
            self.status.set("Не удалось сохранить файл. Текст доступен в окне.")
            messagebox.showerror("Ошибка сохранения", str(exc), parent=self.root)
            return False
        self.status.set("Отменено. Частичный текст сохранён." if self.cancel_event.is_set()
                        else "Готово. Текст сохранён.")
        return True

    def start(self):
        if self.running:
            return
        try:
            audio = Path(self.file.get()).expanduser().resolve()
            if not audio.is_file():
                raise ValueError("Выберите существующий аудио- или видеофайл")
            settings = self.settings()
            try:
                cpu_threads = positive_int(self.cpu_threads.get())
            except ArgumentTypeError:
                raise ValueError("GigaAM CPU threads: введите целое число не меньше 1") from None
        except ValueError as exc:
            messagebox.showerror("Проверьте настройки", str(exc), parent=self.root)
            return
        output = audio.with_name(audio.stem + "-transcript.txt")
        model = "v3_e2e_rnnt" if self.model.get() == "RNNT" else "v3_e2e_ctc"
        device = self.device.get().lower()
        include_timestamps = self.include_timestamps.get()
        cancel_event = self.cancel_event = threading.Event()
        self.run_started_at = time.monotonic()
        self.segments = []
        self.saved_output = None
        self.audio_stats.set("")
        self.progress_started_at = None
        self.estimated_finish_at = None
        self.eta.set("Оценка времени появится после первого фрагмента.")
        self.set_running(True)
        self.set_text("")
        self.status.set("Запуск…")
        self.output.set(str(output))
        self.bar.configure(mode="indeterminate")
        self.bar.start(12)

        def work():
            try:
                run_transcription(audio, output, model, device, settings,
                    status_callback=lambda value: self.events.put(("status", value)),
                    progress_callback=lambda done, total: self.events.put(("progress", (done, total, time.monotonic()))),
                    result_callback=lambda item: self.events.put(("segment", item)),
                    include_timestamps=include_timestamps, cpu_threads=cpu_threads,
                    cancel_callback=cancel_event.is_set,
                    stats_callback=lambda stats: self.events.put(("audio_stats", stats)))
                self.events.put(("cancelled" if cancel_event.is_set() else "done", output))
            except Exception as exc:
                self.events.put(("error", str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            while True:
                event, value = self.events.get_nowait()
                if event == "status":
                    if not self.cancel_event.is_set():
                        self.status.set(value)
                elif event == "segment":
                    self.segments.append(value)
                    self.append_segment(value)
                elif event == "audio_stats":
                    self.audio_stats.set(format_audio_stats(value))
                elif event == "progress":
                    done, total, completed_at = value
                    if not self.cancel_event.is_set():
                        self.update_eta(done, total, completed_at)
                    self.bar.stop()
                    self.bar.configure(mode="determinate", value=100 * done / max(total, 1))
                    if not self.cancel_event.is_set():
                        self.status.set(f"Распознано фрагментов: {done} из {total}…")
                elif event == "cancelled":
                    self.bar.stop()
                    if str(self.bar["mode"]) == "indeterminate":
                        self.bar.configure(mode="determinate", value=0)
                    self.set_running(False)
                    if self.segments:
                        self.saved_output = value
                        self.save_transcript()
                    else:
                        self.status.set("Отменено. Нет распознанных фрагментов.")
                    self.show_elapsed()
                elif event == "done":
                    self.bar.stop()
                    self.bar.configure(mode="determinate", value=100)
                    self.set_running(False)
                    self.saved_output = value
                    if not self.segments:
                        self.set_text("Речь не обнаружена.")
                    self.save_transcript()
                    self.show_elapsed()
                elif event == "error":
                    self.bar.stop()
                    self.bar.configure(mode="determinate", value=0)
                    self.set_running(False)
                    self.status.set("Ошибка распознавания. Полученный текст сохранён в окне.")
                    self.show_elapsed()
                    messagebox.showerror("Ошибка распознавания", value, parent=self.root)
        except queue.Empty:
            pass
        self.refresh_eta()
        self.root.after(100, self.poll)

    def close(self):
        if self.running and not messagebox.askyesno("Остановить распознавание?", "Закрыть приложение и остановить распознавание?", parent=self.root):
            return
        self.root.destroy()


def main():
    root = tk.Tk()
    TranscriberApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
