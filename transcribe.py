"""Small user-facing launcher for the local GigaAM transcription package."""

import argparse
import os
from pathlib import Path
import sys


def format_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    rest = seconds % 60
    if hours:
        return f"{hours:02d}:{minutes:02d}:{rest:06.3f}"
    return f"{minutes:02d}:{rest:06.3f}"


def parser(advanced: bool = False) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Transcribe an audio or video file with GigaAM and Silero VAD."
    )
    p.add_argument("audio", nargs="?", type=Path, help="Input file; a picker opens if omitted")
    p.add_argument("-o", "--output", type=Path, help="Transcript path (default: beside input)")
    p.add_argument("--advanced-help", action="store_true", help="Show advanced settings")
    hidden = None if advanced else argparse.SUPPRESS
    p.add_argument("--model", choices=("v3_e2e_rnnt", "v3_e2e_ctc"),
                   default="v3_e2e_rnnt", help=hidden or "GigaAM model")
    p.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto",
                   help=hidden or "Inference device")
    options = (
        ("max-duration", float, "max_duration", "Maximum preferred segment length in seconds"),
        ("min-duration", float, "min_duration", "Minimum preferred segment length in seconds"),
        ("strict-limit-duration", float, "strict_limit_duration", "Hard segment length limit in seconds"),
        ("new-chunk-threshold", float, "new_chunk_threshold", "Minimum duration to keep a chunk"),
        ("vad-threshold", float, "vad_threshold", "Silero speech probability threshold"),
        ("vad-min-speech-ms", int, "vad_min_speech_ms", "Silero minimum speech duration"),
        ("vad-max-speech-s", float, "vad_max_speech_s", "Silero maximum speech duration"),
        ("vad-min-silence-ms", int, "vad_min_silence_ms", "Silero minimum silence duration"),
        ("vad-window-samples", int, "vad_window_samples", "Silero window size in samples"),
        ("vad-speech-pad-ms", int, "vad_speech_pad_ms", "Silero speech padding"),
    )
    for flag, kind, dest, description in options:
        p.add_argument(f"--{flag}", type=kind, dest=dest, help=hidden or description)
    return p


def choose_file() -> Path | None:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    try:
        selected = filedialog.askopenfilename(title="Choose audio or video to transcribe")
    finally:
        root.destroy()
    return Path(selected) if selected else None


def bundled_model_root(model_name: str) -> Path | None:
    root = Path(__file__).resolve().parent / "models"
    checkpoint = root / f"{model_name}.ckpt"
    tokenizer = root / f"{model_name}_tokenizer.model"
    if checkpoint.is_file() and tokenizer.is_file():
        return root
    return None


def make_vad_kwargs(args: argparse.Namespace) -> dict:
    names = (
        "max_duration", "min_duration", "strict_limit_duration", "new_chunk_threshold",
        "vad_threshold", "vad_min_speech_ms", "vad_max_speech_s", "vad_min_silence_ms",
        "vad_window_samples", "vad_speech_pad_ms",
    )
    return {name: getattr(args, name) for name in names if getattr(args, name) is not None}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = parser(advanced="--advanced-help" in argv).parse_args(argv)
    if args.advanced_help:
        parser(advanced=True).print_help()
        return 0

    picked = args.audio is None
    audio = args.audio or choose_file()
    if audio is None:
        return 0
    audio = audio.expanduser().resolve()
    if not audio.is_file():
        print(f"Input file does not exist: {audio}", file=sys.stderr)
        return 2

    # GigaAM's audio loader calls the external ffmpeg command.
    bundled_bin = Path(__file__).resolve().parent / "bin"
    if (bundled_bin / "ffmpeg.exe").is_file():
        os.environ["PATH"] = str(bundled_bin) + os.pathsep + os.environ.get("PATH", "")

    import gigaam
    import torch

    device = args.device if args.device != "auto" else ("cuda" if torch.cuda.is_available() else "cpu")
    if device == "cuda" and not torch.cuda.is_available():
        print("CUDA was requested but is unavailable on this computer.", file=sys.stderr)
        return 2

    output = (args.output or audio.with_name(audio.stem + ".transcript.txt")).expanduser().resolve()
    print(f"Loading {args.model} on {device}...", flush=True)
    model_root = bundled_model_root(args.model)
    model = gigaam.load_model(args.model, device=device,
                              download_root=str(model_root) if model_root else None)
    print(f"Transcribing {audio.name}...", flush=True)
    segments = model.transcribe_longform(str(audio), **make_vad_kwargs(args))
    lines = [
        f"[{format_time(start)} - {format_time(end)}] {item['transcription']}"
        for item in segments
        for start, end in [item["boundaries"]]
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    print(f"Saved {len(lines)} segments to {output}", flush=True)
    if picked and sys.stdin.isatty():
        input("Press Enter to close...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
