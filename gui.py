"""Minimal Tk interface; all model work runs outside the UI thread."""

from pathlib import Path
import math
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from transcribe import format_segments, run_transcription


# These values match the imported file-based transcription path.
SETTINGS = (
    ("vad_threshold", "Порог речи", float, 0.5),
    ("vad_min_speech_ms", "Минимум речи (мс)", int, 300),
    ("vad_max_speech_s", "Максимум речи (с)", float, 20),
    ("vad_min_silence_ms", "Минимум тишины (мс)", int, 2000),
    ("vad_speech_pad_ms", "Отступы речи (мс)", int, 250),
    ("new_chunk_threshold", "Минимум фрагмента (с)", float, 0.2),
    ("max_duration", "Желаемый максимум (с)", float, 24),
    ("min_duration", "Желаемый минимум (с)", float, 15),
    ("strict_limit_duration", "Жёсткий предел (с)", float, 25),
)


class TranscriberApp:
    def __init__(self, root):
        self.root = root
        self.root.title("GigaAM — Расшифровка речи")
        self.root.geometry("760x480")
        self.root.minsize(640, 440)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.events = queue.Queue()
        self.running = False
        self.advanced_visible = False
        self.file = tk.StringVar()
        self.model = tk.StringVar(value="RNNT")
        self.device = tk.StringVar(value="Авто")
        self.status = tk.StringVar(value="Выберите аудио- или видеофайл.")
        self.output = tk.StringVar(value="Текст будет сохранён рядом с исходным файлом.")
        self.include_timestamps = tk.BooleanVar(value=True)
        self.segments = []
        self.saved_output = None
        self.eta = tk.StringVar()
        self.progress_started_at = None
        self.estimated_finish_at = None
        self.values = {name: tk.StringVar(value=str(default))
                       for name, _, _, default in SETTINGS}
        self.controls = []

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
        self.advanced_button = ttk.Button(actions, text="Настройки >", command=self.toggle_advanced)
        self.advanced_button.pack(side="left", padx=8)
        ttk.Checkbutton(actions, text="Включить таймкоды", variable=self.include_timestamps,
                        command=self.timestamps_changed).pack(side="left", padx=8)

        self.advanced = ttk.LabelFrame(body, text="Дополнительные настройки", padding=10)
        self.advanced.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        for column in (1, 3):
            self.advanced.columnconfigure(column, weight=1)
        ttk.Label(self.advanced, text="Модель").grid(row=0, column=0, sticky="w")
        model = ttk.Combobox(self.advanced, textvariable=self.model, values=("RNNT", "CTC"),
                             state="readonly", width=12)
        model.grid(row=0, column=1, sticky="ew", padx=(8, 20), pady=3)
        ttk.Label(self.advanced, text="Устройство").grid(row=0, column=2, sticky="w")
        device = ttk.Combobox(self.advanced, textvariable=self.device,
                              values=("Авто", "CPU", "CUDA"), state="readonly", width=12)
        device.grid(row=0, column=3, sticky="ew", padx=(8, 0), pady=3)
        self.controls.extend((model, device))
        for index, (name, label, _, _) in enumerate(SETTINGS):
            row, pair = divmod(index, 2)
            column = pair * 2
            ttk.Label(self.advanced, text=label).grid(row=row + 1, column=column, sticky="w", pady=3)
            field = ttk.Entry(self.advanced, textvariable=self.values[name], width=12)
            field.grid(row=row + 1, column=column + 1, sticky="ew", padx=(8, 20 if pair == 0 else 0), pady=3)
            self.controls.append(field)
        ttk.Label(self.advanced, text="Окно Silero: 512 отсчётов (фиксировано моделью)").grid(
            row=6, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Label(self.advanced, text="По умолчанию — RNNT. CTC скачивается при первом запуске.").grid(
            row=7, column=0, columnspan=4, sticky="w", pady=3)
        reset = ttk.Button(self.advanced, text="Сбросить настройки", command=self.reset_defaults)
        reset.grid(row=8, column=0, columnspan=4, sticky="w", pady=(5, 0))
        self.controls.append(reset)
        self.advanced.grid_remove()

        progress = ttk.Frame(body)
        progress.grid(row=4, column=0, sticky="ew", pady=(0, 10))
        self.bar = ttk.Progressbar(progress, mode="determinate", maximum=100)
        self.bar.pack(fill="x")
        ttk.Label(progress, textvariable=self.status, wraplength=700).pack(anchor="w", pady=(5, 0))
        ttk.Label(progress, textvariable=self.eta, wraplength=700).pack(anchor="w")
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

    def browse(self):
        name = filedialog.askopenfilename(parent=self.root, title="Выберите аудио или видео")
        if name:
            self.file.set(name)

    def toggle_advanced(self):
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
        self.device.set("Авто")
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
                raise ValueError("Порог речи должен быть больше 0 и не больше 1")
            if name in ("max_duration", "min_duration", "strict_limit_duration", "vad_max_speech_s") and value == 0:
                raise ValueError(f"«{label}»: значение должно быть больше 0")
            result[name] = value
        return result

    def set_text(self, value):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", value)
        self.text.configure(state="disabled")

    def set_running(self, running):
        self.running = running
        if not running:
            self.estimated_finish_at = None
            self.eta.set("")
        for widget in self.controls:
            state = "disabled" if running else ("readonly" if isinstance(widget, ttk.Combobox) else "normal")
            widget.configure(state=state)

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
        self.set_text(format_segments(self.segments, self.include_timestamps.get()))
        self.text.see("end")

    def timestamps_changed(self):
        # Keep structured results intact; only the view and exported text change.
        self.render_segments()
        if self.saved_output is not None and not self.running:
            self.save_transcript()

    def save_transcript(self):
        try:
            self.saved_output.write_text(
                format_segments(self.segments, self.include_timestamps.get()), encoding="utf-8")
        except OSError as exc:
            self.status.set("Не удалось сохранить файл. Текст доступен в окне.")
            messagebox.showerror("Ошибка сохранения", str(exc), parent=self.root)
            return False
        self.status.set("Готово. Текст сохранён.")
        return True

    def start(self):
        try:
            audio = Path(self.file.get()).expanduser().resolve()
            if not audio.is_file():
                raise ValueError("Выберите существующий аудио- или видеофайл")
            settings = self.settings()
        except ValueError as exc:
            messagebox.showerror("Проверьте настройки", str(exc), parent=self.root)
            return
        output = audio.with_name(audio.stem + "-transcript.txt")
        model = "v3_e2e_rnnt" if self.model.get() == "RNNT" else "v3_e2e_ctc"
        device = {"Авто": "auto", "CPU": "cpu", "CUDA": "cuda"}[self.device.get()]
        include_timestamps = self.include_timestamps.get()
        self.segments = []
        self.saved_output = None
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
                    include_timestamps=include_timestamps)
                self.events.put(("done", output))
            except Exception as exc:
                self.events.put(("error", str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            while True:
                event, value = self.events.get_nowait()
                if event == "status":
                    self.status.set(value)
                elif event == "segment":
                    self.segments.append(value)
                    self.render_segments()
                elif event == "progress":
                    done, total, completed_at = value
                    self.update_eta(done, total, completed_at)
                    self.bar.stop()
                    self.bar.configure(mode="determinate", value=100 * done / max(total, 1))
                    self.status.set(f"Распознано фрагментов: {done} из {total}…")
                elif event == "done":
                    self.bar.stop()
                    self.bar.configure(mode="determinate", value=100)
                    self.set_running(False)
                    self.saved_output = value
                    self.render_segments()
                    if not self.segments:
                        self.set_text("Речь не обнаружена.")
                    self.save_transcript()
                elif event == "error":
                    self.bar.stop()
                    self.bar.configure(mode="determinate", value=0)
                    self.set_running(False)
                    self.status.set("Ошибка распознавания. Полученный текст сохранён в окне.")
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
