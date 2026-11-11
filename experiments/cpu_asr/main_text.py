"""Whole transcript of one file with one engine, as the app makes the main text (plan 08 C4).

    python -I experiments/cpu_asr/main_text.py AUDIO NAME OUT_DIR --engine wcpp|fw|rnnt
        [--fw-folder build/cpu-asr-test/models/fw-turbo-int8] [--language auto] [--threads 8]

Engines:
- wcpp: the app's Whisper (whisper.cpp, ggml large-v3-turbo q5_0) on the CPU;
- wcppg: the same on the Vulkan GPU (for the text of the long files: the CPU reads at about
  real time, the GPU in seconds; the short files show whether the two texts differ);
- fw: faster-whisper large-v3-turbo int8 (gigaam_app.faster_whisper_model) on the CPU;
- fwm: fw, but with no language set it detects the language from the encoder output it
  transcribes with (faster-whisper's multilingual=True; the language argument is only a
  placeholder then), so each chunk is encoded once instead of twice (detect, then transcribe);
- rnnt: GigaAM RNNT on the usual device, the third reading the two Whispers are held against.

The app's Transcriber is used as it is: the same VAD chunks, greedy, nothing carried over
from one chunk to the next, the language detected per chunk unless --language is given.
Writes OUT_DIR/main/ENGINE/NAME.json: segments with words (start, end, text, confidence),
the language Whisper found for each chunk, load and transcription time, RAM after loading
and the peak (the whole process: the decoded audio counts too). Run with the dev venv from
the repository root.
"""

import argparse
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gigaam_app.engine import Transcriber  # noqa: E402
from gigaam_app.paths import models_dir  # noqa: E402


class _MemoryCounters(ctypes.Structure):
    """PROCESS_MEMORY_COUNTERS of psapi (the dev venv has no psutil)."""
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


def memory_mb():
    """(working set, peak working set) of this process in MB, or (None, None) off Windows."""
    try:
        counters = _MemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        kernel32 = ctypes.WinDLL("kernel32")
        # Declared types: without them ctypes passes the process handle (-1) as a 32-bit int.
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.K32GetProcessMemoryInfo.argtypes = (wintypes.HANDLE, ctypes.POINTER(_MemoryCounters), wintypes.DWORD)
        kernel32.K32GetProcessMemoryInfo.restype = wintypes.BOOL
        process = kernel32.GetCurrentProcess()
        if not kernel32.K32GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb):
            return None, None
        return round(counters.WorkingSetSize / 2**20), round(counters.PeakWorkingSetSize / 2**20)
    except (AttributeError, OSError):
        return None, None


def open_engine(engine, fw_folder, language, threads):
    """A Transcriber for the engine, loaded as the app would load it on the CPU."""
    if engine in ("wcpp", "wcppg"):
        return Transcriber("Whisper", device="cpu" if engine == "wcpp" else "gpu", cpu_threads=threads,
                           language=language)
    if engine in ("fw", "fwm"):
        # model_root gives the VAD model; an absolute model path stays as it is under it.
        transcriber = Transcriber(str(Path(fw_folder).resolve()), device="cpu", cpu_threads=threads,
                                  model_root=models_dir(), language=language)
        if engine == "fwm":
            original_transcribe = transcriber.asr.model.transcribe

            def transcribe_once(audio, language=None, **options):
                # No language: per-segment detection on the transcription's own encoder output.
                if language is None:
                    return original_transcribe(audio, language="en", multilingual=True, **options)
                return original_transcribe(audio, language=language, **options)

            transcriber.asr.model.transcribe = transcribe_once
        return transcriber
    return Transcriber("RNNT", device="auto")


def script_of(words):
    """'ru' when a chunk's text is mostly Cyrillic, 'latin' when mostly Latin, '' when empty
    (fwm cannot report the language it detected: faster-whisper's segments do not carry it)."""
    text = "".join(word.word for word in words)
    latin = sum("a" <= ch.lower() <= "z" for ch in text)
    cyrillic = sum("Ѐ" <= ch <= "ӿ" for ch in text)
    if not latin + cyrillic:
        return ""
    return "ru" if cyrillic >= latin else "latin"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audio")
    parser.add_argument("name")
    parser.add_argument("out_dir")
    parser.add_argument("--engine", choices=("wcpp", "wcppg", "fw", "fwm", "rnnt"), required=True)
    parser.add_argument("--fw-folder", default="build/cpu-asr-test/models/fw-turbo-int8")
    parser.add_argument("--language", default="auto")
    parser.add_argument("--threads", type=int, default=8)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    transcriber = open_engine(args.engine, args.fw_folder, args.language, args.threads)
    ram_loaded, _ = memory_mb()
    languages = []
    if transcriber.uses_language:
        # Keep the language Whisper found for every chunk (the first item of each result).
        original_encode = transcriber.asr.encode

        def encode_and_note(pieces, should_cancel=None, prompt=None):
            results = original_encode(pieces, should_cancel, prompt)
            if args.engine == "fwm":
                languages.extend(script_of(result[1]) for result in results)
            else:
                languages.extend(result[0] for result in results)
            return results

        transcriber.asr.encode = encode_and_note

    last_report = [time.perf_counter()]

    def progress(searched, recognised):
        if time.perf_counter() - last_report[0] > 60:
            last_report[0] = time.perf_counter()
            print(f"  {args.name} {args.engine}: {100 * recognised:.0f}% recognised", flush=True)

    started = time.perf_counter()
    transcript = transcriber.transcribe(args.audio, on_progress=progress)
    elapsed = time.perf_counter() - started
    _, ram_peak = memory_mb()

    data = {
        "engine": args.engine, "name": args.name, "audio": str(args.audio), "model": transcriber.model_label,
        "device": transcriber.device_label, "threads": args.threads, "language_setting": args.language,
        "load_seconds": round(transcriber.load_seconds, 2), "seconds": round(elapsed, 1),
        "audio_seconds": transcript.audio_seconds, "speech_seconds": transcript.speech_seconds,
        "recognised_seconds": transcript.recognised_seconds,
        "ram_loaded_mb": ram_loaded, "ram_peak_mb": ram_peak, "chunk_languages": languages,
        "segments": [{"start": s.start, "end": s.end, "text": s.text,
                      "words": [[w.start, w.end, w.text, w.confidence] for w in s.words]}
                     for s in transcript.segments],
    }
    out = Path(args.out_dir) / "main" / args.engine / f"{args.name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    words = sum(len(s.words) for s in transcript.segments)
    print(f"{args.name} {args.engine}: {elapsed:.1f} s for {transcript.audio_seconds:.0f} s of audio "
          f"(load {transcriber.load_seconds:.1f} s), {len(transcript.segments)} lines, {words} words, "
          f"RAM {ram_loaded} -> peak {ram_peak} MB -> {out}")


if __name__ == "__main__":
    main()
