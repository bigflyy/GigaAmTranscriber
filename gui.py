"""Minimal Tk interface; all model work runs outside the UI thread."""

from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from transcribe import run_transcription


# These values match the imported file-based transcription path.
SETTINGS = (
    ("vad_threshold", "Speech threshold", float, 0.5),
    ("vad_min_speech_ms", "Minimum speech (ms)", int, 300),
    ("vad_max_speech_s", "Maximum speech (s)", float, 20),
    ("vad_min_silence_ms", "Minimum silence (ms)", int, 2000),
    ("vad_speech_pad_ms", "Speech padding (ms)", int, 250),
    ("new_chunk_threshold", "Minimum chunk (s)", float, 0.2),
    ("max_duration", "Preferred max chunk (s)", float, 24),
    ("min_duration", "Preferred min chunk (s)", float, 15),
    ("strict_limit_duration", "Hard chunk limit (s)", float, 25),
)


class TranscriberApp:
    def __init__(self, root):
        self.root = root
        self.root.title("GigaAM Transcriber")
        self.root.geometry("760x480")
        self.root.minsize(640, 440)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.events = queue.Queue()
        self.running = False
        self.advanced_visible = False
        self.file = tk.StringVar()
        self.model = tk.StringVar(value="RNNT")
        self.device = tk.StringVar(value="auto")
        self.status = tk.StringVar(value="Choose an audio or video file.")
        self.output = tk.StringVar(value="Transcript will be saved beside the input file.")
        self.values = {name: tk.StringVar(value=str(default))
                       for name, _, _, default in SETTINGS}
        self.controls = []

        body = ttk.Frame(root, padding=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(5, weight=1)
        ttk.Label(body, text="GigaAM Transcriber", font=("Segoe UI", 15, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 10))

        files = ttk.Frame(body)
        files.grid(row=1, column=0, sticky="ew")
        files.columnconfigure(0, weight=1)
        entry = ttk.Entry(files, textvariable=self.file)
        entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        browse = ttk.Button(files, text="Choose file...", command=self.browse)
        browse.grid(row=0, column=1)
        self.controls.extend((entry, browse))

        actions = ttk.Frame(body)
        actions.grid(row=2, column=0, sticky="ew", pady=10)
        self.start_button = ttk.Button(actions, text="Transcribe", command=self.start)
        self.start_button.pack(side="left")
        self.controls.append(self.start_button)
        self.advanced_button = ttk.Button(actions, text="Advanced settings >", command=self.toggle_advanced)
        self.advanced_button.pack(side="left", padx=8)

        self.advanced = ttk.LabelFrame(body, text="Advanced settings", padding=10)
        self.advanced.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        for column in (1, 3):
            self.advanced.columnconfigure(column, weight=1)
        ttk.Label(self.advanced, text="Model").grid(row=0, column=0, sticky="w")
        model = ttk.Combobox(self.advanced, textvariable=self.model, values=("RNNT", "CTC"),
                             state="readonly", width=12)
        model.grid(row=0, column=1, sticky="ew", padx=(8, 20), pady=3)
        ttk.Label(self.advanced, text="Device").grid(row=0, column=2, sticky="w")
        device = ttk.Combobox(self.advanced, textvariable=self.device,
                              values=("auto", "cpu", "cuda"), state="readonly", width=12)
        device.grid(row=0, column=3, sticky="ew", padx=(8, 0), pady=3)
        self.controls.extend((model, device))
        for index, (name, label, _, _) in enumerate(SETTINGS):
            row, pair = divmod(index, 2)
            column = pair * 2
            ttk.Label(self.advanced, text=label).grid(row=row + 1, column=column, sticky="w", pady=3)
            field = ttk.Entry(self.advanced, textvariable=self.values[name], width=12)
            field.grid(row=row + 1, column=column + 1, sticky="ew", padx=(8, 20 if pair == 0 else 0), pady=3)
            self.controls.append(field)
        ttk.Label(self.advanced, text="Silero analysis window: 512 samples (fixed by this model)").grid(
            row=6, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Label(self.advanced, text="CTC downloads its model on first use. RNNT is the default.").grid(
            row=7, column=0, columnspan=4, sticky="w", pady=3)
        reset = ttk.Button(self.advanced, text="Reset defaults", command=self.reset_defaults)
        reset.grid(row=8, column=0, columnspan=4, sticky="w", pady=(5, 0))
        self.controls.append(reset)
        self.advanced.grid_remove()

        progress = ttk.Frame(body)
        progress.grid(row=4, column=0, sticky="ew", pady=(0, 10))
        self.bar = ttk.Progressbar(progress, mode="determinate", maximum=100)
        self.bar.pack(fill="x")
        ttk.Label(progress, textvariable=self.status, wraplength=700).pack(anchor="w", pady=(5, 0))
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
        name = filedialog.askopenfilename(parent=self.root, title="Choose audio or video")
        if name:
            self.file.set(name)

    def toggle_advanced(self):
        self.advanced_visible = not self.advanced_visible
        if self.advanced_visible:
            self.advanced.grid()
            self.root.geometry("760x790")
            self.advanced_button.configure(text="Advanced settings v")
        else:
            self.advanced.grid_remove()
            self.root.geometry("760x480")
            self.advanced_button.configure(text="Advanced settings >")

    def reset_defaults(self):
        self.model.set("RNNT")
        self.device.set("auto")
        for name, _, _, default in SETTINGS:
            self.values[name].set(str(default))

    def settings(self):
        result = {}
        for name, label, kind, _ in SETTINGS:
            try:
                value = kind(self.values[name].get())
            except ValueError:
                raise ValueError(f"{label} must be a number") from None
            if not (0 <= value < float("inf")):
                raise ValueError(f"{label} must be a finite, non-negative number")
            if name == "vad_threshold" and not 0 < value <= 1:
                raise ValueError("Speech threshold must be greater than 0 and at most 1")
            if name in ("max_duration", "min_duration", "strict_limit_duration", "vad_max_speech_s") and value == 0:
                raise ValueError(f"{label} must be greater than 0")
            result[name] = value
        return result

    def set_text(self, value):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", value)
        self.text.configure(state="disabled")

    def set_running(self, running):
        self.running = running
        for widget in self.controls:
            state = "disabled" if running else ("readonly" if isinstance(widget, ttk.Combobox) else "normal")
            widget.configure(state=state)

    def start(self):
        try:
            audio = Path(self.file.get()).expanduser().resolve()
            if not audio.is_file():
                raise ValueError("Choose an existing audio or video file")
            settings = self.settings()
        except ValueError as exc:
            messagebox.showerror("Check settings", str(exc), parent=self.root)
            return
        output = audio.with_name(audio.stem + ".transcript.txt")
        model = "v3_e2e_rnnt" if self.model.get() == "RNNT" else "v3_e2e_ctc"
        device = self.device.get()
        self.set_running(True)
        self.set_text("")
        self.status.set("Starting...")
        self.output.set(str(output))
        self.bar.configure(mode="indeterminate")
        self.bar.start(12)

        def work():
            try:
                run_transcription(audio, output, model, device, settings,
                    status_callback=lambda value: self.events.put(("status", value)),
                    progress_callback=lambda done, total: self.events.put(("progress", (done, total))))
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
                elif event == "progress":
                    done, total = value
                    self.bar.stop()
                    self.bar.configure(mode="determinate", value=100 * done / max(total, 1))
                    self.status.set(f"Transcribing segment {done} of {total}...")
                elif event == "done":
                    self.bar.stop()
                    self.bar.configure(mode="determinate", value=100)
                    self.set_running(False)
                    transcript = value.read_text(encoding="utf-8")
                    self.set_text(transcript or "No speech was detected.")
                    self.status.set("Done. Transcript saved.")
                elif event == "error":
                    self.bar.stop()
                    self.bar.configure(mode="determinate", value=0)
                    self.set_running(False)
                    self.status.set("Transcription failed.")
                    self.set_text(value)
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def close(self):
        if self.running and not messagebox.askyesno("Stop transcription?", "Close the app and stop the current transcription?", parent=self.root):
            return
        self.root.destroy()


def main():
    root = tk.Tk()
    TranscriberApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
