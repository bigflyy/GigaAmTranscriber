"""Whisper decoding variants on the app's VAD chunks: beam search and a term list as prompt.

    python experiments/whisper/variants.py AUDIO GIGAAM.json OUT_FOLDER --name NAME
        --model-root FOLDER [--model whisper_large_v3_turbo_q5_0] [--language auto]
        [--terms "LLM, fine tuning"] [--other-terms "..."] [--only greedy,beam5,...]

Loads the app's Transcriber with Whisper once and runs the same file several times,
changing only the whisper_full parameters:

- greedy:            the app's current decoding (baseline, also re-measures time)
- beam5:             beam search, 5 beams (whisper.cpp's default beam size)
- greedy+terms:      greedy with --terms as initial_prompt (the user's own term list)
- beam5+terms:       both
- greedy+wrongterms: greedy with --other-terms (a list from another subject), to see
                     whether a prompt that does not fit pushes its words into the text

whisper.cpp clears the carried text (no_context) before it adds initial_prompt, and
each VAD chunk is one call, so the prompt is in front of every chunk. Each variant is
saved as OUT_FOLDER/NAME-VARIANT.json (chunk format of app_engine.py, compare.py reads it)
and compared with the GigaAM reference; a summary goes to OUT_FOLDER/NAME-summary.json.
Run from the repository root with the dev venv.
"""

import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gigaam_app import whisper_cpp  # noqa: E402
from gigaam_app.engine import Transcriber  # noqa: E402
import compare  # noqa: E402

SAMPLING_BEAM_SEARCH = 1  # enum whisper_sampling_strategy


def install_params_override(library):
    """Make Context.transcribe's whisper_full_default_params call return our variant.

    Returns a dict: set "beam" (bool) and "prompt" (str or None) before each run.
    The prompt bytes are kept in the dict so the pointer stays valid during whisper_full.
    """
    original = library.whisper.whisper_full_default_params
    state = {"beam": False, "prompt": None, "_prompt_bytes": None}

    def default_params(strategy):
        params = original(SAMPLING_BEAM_SEARCH if state["beam"] else strategy)
        if state["prompt"]:
            state["_prompt_bytes"] = state["prompt"].encode("utf-8")
            params.initial_prompt = state["_prompt_bytes"]
        return params

    library.whisper.whisper_full_default_params = default_params
    return state


def term_counts(text, groups):
    """For each term: how often the right spelling and the known wrong ones occur."""
    low = text.lower().replace("ё", "е")
    return {name: {"right": sum(low.count(s) for s in right), "wrong": sum(low.count(s) for s in wrong)}
            for name, (right, wrong) in groups.items()}


# Spellings seen in the greedy runs of session 10-11 (wrong) and the intended terms (right).
TERM_GROUPS = {
    "lecture": {
        "boilerplate": (["boilerplate", "бойлерплейт"], ["baylor", "бейлор"]),
        "DeepSeek": (["deepseek", "дипсик"], ["deepsync", "дипсинк"]),
        "Lean": (["lean"], ["lind", "лин "]),
        "ИИ-агент": (["ии-агент", "ии агент", "ai-агент"], ["еагент"]),
        "prompt engineering": (["prompt engineering", "промпт-инжиниринг", "промпт инжиниринг"], ["prompt инжиниринг"]),
        "fine tuning": (["fine tuning", "fine-tuning", "файн-тюнинг"], []),
        "LLM": (["llm"], []),
    },
    "call": {
        "Ethernet": (["ethernet"], ["изернет", "мазернет"]),
        "Пуассон": (["пуассон"], ["паосон", "по ассо", "полосон", "по сону"]),
        "коллизия": (["коллизи"], []),
        "CSMA": (["csma"], []),
    },
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audio")
    parser.add_argument("reference")
    parser.add_argument("out_folder")
    parser.add_argument("--name", required=True, help="lecture or call: picks the term spellings to count")
    parser.add_argument("--model-root", required=True)
    parser.add_argument("--model", default="whisper_large_v3_turbo_q5_0")
    parser.add_argument("--language", default="auto")
    parser.add_argument("--terms", default="")
    parser.add_argument("--other-terms", default="")
    parser.add_argument("--only", default="")
    args = parser.parse_args()

    variants = [("greedy", False, None), ("beam5", True, None)]
    if args.terms:
        variants += [("greedy+terms", False, args.terms), ("beam5+terms", True, args.terms)]
    if args.other_terms:
        variants.append(("greedy+wrongterms", False, args.other_terms))
    if args.only:
        wanted = set(args.only.split(","))
        variants = [v for v in variants if v[0] in wanted]

    out = Path(args.out_folder)
    out.mkdir(parents=True, exist_ok=True)
    ref_text, _ = compare.load_text(args.reference)
    ref_words = compare.words(ref_text)

    transcriber = Transcriber(args.model, device="auto", model_root=args.model_root, language=args.language)
    state = install_params_override(whisper_cpp.Library.get())
    summary = {"audio": args.audio, "device": transcriber.device_label,
               "gpu": getattr(transcriber.asr, "gpu_name", None), "variants": {}}
    for variant, beam, prompt in variants:
        state["beam"], state["prompt"] = beam, prompt
        languages = []
        started = time.perf_counter()
        transcript = transcriber.transcribe(
            args.audio, on_segment=lambda s: languages.append(getattr(transcriber.asr, "last_language", "")))
        seconds = time.perf_counter() - started
        chunks = [{"start": s.start, "end": s.end, "text": s.text, "language": lang}
                  for s, lang in zip(transcript.segments, languages)]
        (out / f"{args.name}-{variant}.json").write_text(
            json.dumps({"variant": variant, "prompt": prompt, "transcribe_seconds": round(seconds, 2),
                        "chunks": chunks}, ensure_ascii=False, indent=1), encoding="utf-8")
        text = " ".join(c["text"] for c in chunks)
        other_words = compare.words(text)
        _, errors, digit_errors = compare.compare(ref_words, other_words)
        not_language = sorted({c["language"] for c in chunks} - {"ru"})
        result = {
            "seconds": round(seconds, 1),
            "words": len(other_words),
            "differ_percent": round(100 * errors / max(1, len(ref_words)), 2),
            "differ_percent_without_digits": round(100 * (errors - digit_errors) / max(1, len(ref_words)), 2),
            "loops": [(gram, count) for _, gram, count in compare.repeated_runs(other_words)],
            "chunks_not_ru": sum(1 for c in chunks if c["language"] != "ru"),
            "languages_not_ru": not_language,
            "terms": term_counts(text, TERM_GROUPS.get(args.name, {})),
        }
        summary["variants"][variant] = result
        print(variant, json.dumps(result, ensure_ascii=False), flush=True)
    (out / f"{args.name}-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
