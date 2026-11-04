"""Command line: gigaam-cli FILE [FILE ...]. The model loads once for all files."""

import argparse
from dataclasses import fields
import glob
from pathlib import Path
import sys
import time

from . import __version__, config
from .engine import MODELS, Transcriber
from .outputs import FORMATS, write_outputs
from .vad import VadOptions


def build_parser():
    parser = argparse.ArgumentParser(
        prog="gigaam-cli",
        description="Transcribe Russian speech in audio or video files with GigaAM.")
    parser.add_argument("files", nargs="+", type=Path, help="audio or video files")
    parser.add_argument("-o", "--out-dir", type=Path, help="output folder (default: beside each file)")
    parser.add_argument("--model", choices=tuple(MODELS), help="recognition model (default: RNNT)")
    parser.add_argument("--device", choices=("auto", "gpu", "cpu"), help="default: auto")
    parser.add_argument("--threads", type=int, help="CPU threads for recognition (default: automatic)")
    parser.add_argument("--formats", help=f"comma-separated list from {','.join(FORMATS)} "
                                          "(default: txt,timestamps)")
    parser.add_argument("--config", type=Path, help="settings file (default: gigaam-config.json beside the app)")
    parser.add_argument("--quiet", action="store_true", help="print only errors")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    tuning = parser.add_argument_group("segmentation (override the settings file)")
    for item in fields(VadOptions):
        tuning.add_argument("--" + item.name.replace("_", "-"), type=item.type, dest=item.name)
    return parser


def expand_wildcards(paths):
    """cmd.exe and PowerShell pass *.mp3 through unexpanded; expand it here, keeping the order."""
    expanded = []
    for path in paths:
        text = str(path)
        matches = sorted(glob.glob(text)) if glob.has_magic(text) else []
        expanded += [Path(match) for match in matches if Path(match).is_file()] or [path]
    return expanded


def safe_console():
    """A redirected console uses the ANSI code page, which lacks many characters of
    file names; print those as escapes instead of failing after the work is done."""
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")


def main(argv=None):
    safe_console()
    args = build_parser().parse_args(argv)
    args.files = expand_wildcards(args.files)
    try:
        settings = config.load(args.config)
    except (OSError, ValueError) as error:
        print(f"Settings error: {error}", file=sys.stderr)
        return 2
    model = args.model or settings.model
    device = args.device or settings.engine_device
    threads = args.threads if args.threads is not None else (settings.cpu_threads or None)
    formats = args.formats.split(",") if args.formats else settings.outputs
    unknown = [fmt for fmt in formats if fmt not in FORMATS]
    if unknown:
        print(f"Unknown format: {', '.join(unknown)}", file=sys.stderr)
        return 2
    options = settings.vad
    for item in fields(VadOptions):
        value = getattr(args, item.name)
        if value is not None:
            setattr(options, item.name, value)

    def say(message):
        if not args.quiet:
            print(message, flush=True)

    missing = [str(path) for path in args.files if not path.is_file()]
    if missing:
        print("File not found: " + ", ".join(missing), file=sys.stderr)
        return 2
    transcriber = Transcriber(model, device=device, cpu_threads=threads)
    say(f"{model} on {transcriber.device_label}, loaded in {transcriber.load_seconds:.1f} s")
    failures = 0
    for path in args.files:
        try:
            last = [0.0]

            def progress(searched, recognised):
                now = time.perf_counter()
                if not args.quiet and sys.stderr.isatty() and now - last[0] > 0.2:
                    last[0] = now
                    print(f"\r  searched {searched * 100:5.1f}%  recognised {recognised * 100:5.1f}%",
                          end="", file=sys.stderr, flush=True)

            result = transcriber.transcribe(path, options, on_progress=progress)
            if not args.quiet and sys.stderr.isatty():
                print("\r" + " " * 40 + "\r", end="", file=sys.stderr)
            if not result.segments:
                say(f"{path.name}: no speech found, nothing written")
                continue
            written = write_outputs(result, formats, args.out_dir)
            speed = result.audio_seconds / result.elapsed_seconds if result.elapsed_seconds else 0
            say(f"{path.name}: {result.audio_seconds:.0f} s of audio in {result.elapsed_seconds:.1f} s "
                f"({speed:.0f}x realtime)")
            for item in written:
                say(f"  {item}")
        except Exception as error:  # report and continue with the next file
            failures += 1
            print(f"{path}: {error}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
