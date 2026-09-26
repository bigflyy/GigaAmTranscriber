"""English technical help shared by hover hints and the full help window."""

import tkinter as tk


OVERVIEW = (
    "How the settings work\n\n"
    "The app decodes the file to mono audio at 16 kHz. Silero VAD (Voice Activity "
    "Detection) first finds speech regions. A second step groups those regions "
    "into audio chunks for GigaAM. GigaAM then transcribes each chunk and displays "
    "its text. VAD settings control speech detection; chunk settings control what "
    "is sent to the speech recognizer. They act at different stages.\n\n"
    "Durations marked ms are milliseconds: 1000 ms = 1 second. Durations marked "
    "s are seconds. Use a decimal point for fractional values, for example 0.5. "
    "Chunk duration is the time span from its start to its end and can include "
    "silence between speech regions.\n\n"
    "Start with the defaults and change one setting at a time on a representative "
    "recording. Shorter chunks can show partial text sooner once VAD finishes, "
    "but the whole file is still scanned for speech before transcription starts. "
    "Progress counts completed chunks. Remaining time is an estimate based on "
    "completed chunks, so unequal chunk lengths can make it change."
)

HELP = {
    "model": ("Model", (
        "Default: RNNT (v3_e2e_rnnt).\n\n"
        "Selects the GigaAM speech-recognition model that turns detected speech "
        "into text. RNNT uses a Recurrent Neural Network Transducer decoding head; "
        "CTC uses Connectionist Temporal Classification. These are alternative "
        "recognition models, and their wording, punctuation and speed can differ. "
        "Neither choice changes the Silero detection settings.\n\n"
        "The Windows release includes RNNT and its tokenizer, so the default "
        "model works offline. CTC is downloaded and cached on first use; this "
        "requires an internet connection and additional disk space. Select RNNT "
        "to reproduce the original setup. Compare both models on your own audio "
        "if you want to choose based on transcription quality."
    )),
    "device": ("Device", (
        "Default: Auto. Choices: Auto, CPU, CUDA.\n\n"
        "Auto uses CUDA when this build and the computer make CUDA available; "
        "otherwise it uses the CPU. CPU forces recognition on the processor. "
        "CUDA requests an NVIDIA GPU explicitly and reports an error if it is "
        "unavailable. It requires a CUDA-enabled build, a supported NVIDIA GPU "
        "and a compatible driver.\n\n"
        "The small CPU-only EXE cannot use CUDA, even on a computer with an "
        "NVIDIA GPU. Choose Auto or CPU in that build. Silero still runs on the "
        "CPU with one thread; this selector changes the GigaAM recognition device. "
        "The GigaAM CPU threads field takes effect when recognition uses CPU."
    )),
    "vad_threshold": ("VAD threshold", (
        "Default: 0.5. Range in this app: greater than 0 and at most 1.\n\n"
        "Silero estimates how likely each small audio window is to contain speech. "
        "This threshold controls when it starts treating audio as speech. It is "
        "a detection threshold, not a transcription-confidence score.\n\n"
        "Increasing it makes detection stricter: it may reject more background "
        "noise, but can also miss quiet, distant or unclear speech. Decreasing "
        "it makes detection more permissive and can recover weak speech while "
        "also admitting more noise or music. Silero uses a separate internal "
        "exit threshold to avoid rapidly switching speech on and off.\n\n"
        "For example, try 0.4 if quiet phrases are missing, or 0.6 if noise is "
        "regularly treated as speech. These are starting points to compare, "
        "not guaranteed improvements."
    )),
    "vad_min_speech_ms": ("VAD min speech (ms)", (
        "Default: 300 ms (0.3 seconds).\n\n"
        "Silero discards detected speech regions shorter than this duration. "
        "This helps filter brief noises that resemble speech. It applies to "
        "detected speech regions before the app groups them into GigaAM chunks.\n\n"
        "A larger value removes more short detections, but can lose brief words, "
        "interjections or short answers. A smaller value preserves more short "
        "utterances and may also keep clicks, breaths or other unwanted sounds. "
        "For example, reducing 300 to 150 ms is worth comparing if very short "
        "answers disappear. This setting does not impose a minimum sentence "
        "length and does not pad short speech to make it longer."
    )),
    "vad_max_speech_s": ("VAD max speech (s)", (
        "Default: 20 seconds.\n\n"
        "Limits the length of a speech region produced by Silero. When a long "
        "stretch of speech reaches this limit, Silero looks for a suitable short "
        "silence near the split; if none is available, it cuts the region anyway.\n\n"
        "Lower values create more VAD regions and more opportunities for the "
        "grouping step to form short chunks. Higher values allow longer speech "
        "regions before VAD splits them. A forced split can occur inside a word "
        "if the speaker does not pause.\n\n"
        "The final GigaAM chunk length is controlled separately: the grouping "
        "step can combine VAD regions, and Hard chunk limit can split the result. "
        "Do not interpret this field as the exact duration of every final chunk."
    )),
    "vad_min_silence_ms": ("VAD min silence (ms)", (
        "Default: 2000 ms (2 seconds).\n\n"
        "The silence duration Silero normally waits for before ending a speech "
        "region. Pauses shorter than this tend to stay inside the same region. "
        "The maximum-speech-duration rule can still force a split sooner.\n\n"
        "Increasing the value keeps speech separated by longer pauses together. "
        "Decreasing it separates speech at shorter pauses and usually creates "
        "more regions. For example, 500 ms reacts to half-second pauses, whereas "
        "the default normally waits for a two-second pause.\n\n"
        "This is not a delay added after every phrase during playback. The app "
        "processes a file, and it does not detect speaker changes. Also, the "
        "chunk-grouping step may join nearby VAD regions again."
    )),
    "vad_speech_pad_ms": ("VAD speech padding (ms)", (
        "Default: 250 ms (0.25 seconds on each side).\n\n"
        "Adds a margin around detected speech so that the recognizer receives "
        "a little audio before the detected start and after the detected end. "
        "This can protect quiet beginnings or trailing consonants that VAD "
        "might otherwise cut off.\n\n"
        "Larger padding includes more surrounding silence or noise and can "
        "increase the amount of audio sent to GigaAM. Smaller padding gives "
        "tighter boundaries but less protection at the edges. For example, "
        "250 ms aims to add a quarter-second margin to both ends; the available "
        "margin may be reduced near neighboring regions or the file edges. "
        "It does not insert artificial silence into the recording."
    )),
    "new_chunk_threshold": ("Min chunk duration (s)", (
        "Default: 0.2 seconds. Internal name: new_chunk_threshold.\n\n"
        "This is a cutoff used by the app's chunk-grouping step, after Silero "
        "has detected speech. An accumulated chunk must exceed this duration "
        "before it is finalized at a grouping boundary. At the end of the file, "
        "a remaining chunk at or below the cutoff is discarded. Earlier tiny "
        "regions can remain in the accumulator and be combined with later ones.\n\n"
        "The duration is the accumulated time span and can include gaps. Raising "
        "the cutoff can discard a short final utterance; lowering it allows "
        "smaller remainders to be transcribed. This differs from VAD min speech, "
        "which filters individual detected speech regions earlier in the pipeline. "
        "It is not a confidence threshold or a required sentence length."
    )),
    "max_duration": ("Preferred max chunk (s)", (
        "Default: 24 seconds.\n\n"
        "A grouping target for the final chunks sent to GigaAM. Before adding "
        "the next VAD region, the app checks whether the resulting time span "
        "would exceed this value. If the current chunk is large enough to keep, "
        "it finishes that chunk and starts the next one. Gaps between regions "
        "count toward the span.\n\n"
        "For example, adding a region that extends a 16-second chunk to 27 "
        "seconds would normally start a new chunk with the default of 24. "
        "A single long VAD region can still exceed this preferred target; Hard "
        "chunk limit is the separate final safeguard. Smaller targets generally "
        "mean more chunks and shorter per-chunk waits, with more decoding overhead."
    )),
    "min_duration": ("Preferred min chunk (s)", (
        "Default: 15 seconds.\n\n"
        "A soft grouping target. Once the current accumulated chunk exceeds "
        "this duration, the next VAD region begins a new chunk instead of being "
        "added to the current one. This makes the app prefer speech-region "
        "boundaries after it has collected enough audio.\n\n"
        "It is not an enforced minimum: chunks can be shorter because the "
        "preferred maximum is reached, the file ends, or the hard limit splits "
        "a long chunk. For example, a 16-second accumulated chunk will normally "
        "be finalized before the next region when this setting is 15.\n\n"
        "Lower values tend to create more, shorter chunks; higher values let "
        "more regions accumulate. A useful starting relationship is preferred "
        "min <= preferred max <= hard limit, as in the defaults 15 / 24 / 25."
    )),
    "strict_limit_duration": ("Hard chunk limit (s)", (
        "Default: 25 seconds.\n\n"
        "The final duration limit applied to a chunk before recognition. When "
        "an accumulated chunk exceeds it, the app divides the chunk into equal "
        "time slices so that each slice is within the limit. This step does not "
        "search for silence or word boundaries.\n\n"
        "For example, a 40-second chunk is split into two approximately "
        "20-second chunks when the limit is 25. Lower limits bound the amount "
        "of audio processed at once, but may cut through words and create more "
        "recognition calls. Higher limits permit longer chunks and can require "
        "more memory and time per call.\n\n"
        "Keep the preferred chunk targets below this limit when practical. "
        "Changing only the hard limit does not change Silero's speech detection."
    )),
    "cpu_threads": ("GigaAM CPU threads", (
        "Default: 4. Enter a positive integer.\n\n"
        "Sets how many CPU threads PyTorch can use within GigaAM operations "
        "during CPU recognition. It does not reserve specific cores or process "
        "several files at once. Silero uses one thread, and this choice is "
        "applied after speech detection. It has no effect on CUDA recognition.\n\n"
        "More threads can improve throughput, but synchronization overhead and "
        "competition for CPU resources can make high counts slower. On the "
        "tested Ryzen 7 7840HS, a 60-second sample took about 6.70 seconds with "
        "4 threads and 4.64 seconds with 8; 16 was slightly slower than 8. "
        "These are local measurements, not a guarantee for other hardware.\n\n"
        "Try 4 and 8 on your own files. Choose 1 to reproduce the original "
        "single-thread recognition setting. Changes apply to the next run."
    )),
    "silero_runtime": ("Silero runtime and window size", (
        "Fixed in this app: 1 CPU thread, 512 samples per analysis window.\n\n"
        "The audio is decoded at 16,000 samples per second, so a 512-sample "
        "analysis window covers 32 ms. This is Silero's small internal processing "
        "window, not the multi-second chunks sent to GigaAM.\n\n"
        "Silero 6.2.1 ignores its old window_size_samples argument; changing "
        "that deprecated argument would not change the actual window. The app "
        "therefore displays the fixed value. Silero is kept at one CPU thread "
        "because extra threads can add overhead for its small operations. Use "
        "GigaAM CPU threads to tune recognition separately. Both values here "
        "are information, not editable settings."
    )),
}


class HoverHint:
    """Show a non-modal, screen-bounded hint without taking keyboard focus."""

    def __init__(self, widget, title, description):
        self.widget = widget
        self.title = title
        self.description = description
        self.pending = None
        self.window = None
        for event in ("<Enter>", "<FocusIn>"):
            widget.bind(event, self.schedule, add="+")
        for event in ("<Leave>", "<FocusOut>", "<ButtonPress>", "<KeyPress>", "<Destroy>"):
            widget.bind(event, self.hide, add="+")

    def schedule(self, _event=None):
        self.hide()
        self.pending = self.widget.after(550, self.show)

    def show(self):
        self.pending = None
        if not self.widget.winfo_exists() or not self.widget.winfo_ismapped():
            return
        self.window = tip = tk.Toplevel(self.widget)
        tip.withdraw()
        tip.overrideredirect(True)
        tip.attributes("-topmost", True)
        tk.Label(tip, text=self.title + "\n\n" + self.description,
                 justify="left", wraplength=500, background="#fffbe8",
                 foreground="#202020", relief="solid", borderwidth=1,
                 padx=12, pady=10, font=("Segoe UI", 9)).pack()
        tip.update_idletasks()
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        x = max(0, min(x, tip.winfo_screenwidth() - tip.winfo_reqwidth() - 8))
        if y + tip.winfo_reqheight() > tip.winfo_screenheight() - 8:
            y = max(0, self.widget.winfo_rooty() - tip.winfo_reqheight() - 8)
        tip.geometry(f"+{x}+{y}")
        tip.deiconify()

    def hide(self, _event=None):
        if self.pending is not None:
            try:
                self.widget.after_cancel(self.pending)
            except tk.TclError:
                pass
            self.pending = None
        if self.window is not None:
            try:
                self.window.destroy()
            except tk.TclError:
                pass
            self.window = None
