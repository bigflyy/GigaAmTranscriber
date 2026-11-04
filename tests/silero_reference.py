"""Reference: silero-vad 6.2.1 get_speech_timestamps post-processing as one batch.

This is a direct port (MIT licence, Silero Team) kept only for tests: the app
uses the streaming gigaam_app.vad.ChunkFinder, which must give identical
regions and chunks.
"""

from gigaam_app.audio import SAMPLE_RATE
from gigaam_app.vad import WINDOW, VadOptions


def speech_regions(probabilities, n_samples, options: VadOptions):
    """Speech regions as (start, end) sample indices.

    Port of silero_vad.get_speech_timestamps post-processing with
    use_max_poss_sil_at_max_speech=True; the comments follow the original.
    """
    min_speech = SAMPLE_RATE * options.vad_min_speech_ms / 1000
    pad = SAMPLE_RATE * options.vad_speech_pad_ms / 1000
    max_speech = SAMPLE_RATE * options.vad_max_speech_s - WINDOW - 2 * pad
    min_silence = SAMPLE_RATE * options.vad_min_silence_ms / 1000
    min_silence_at_max_speech = SAMPLE_RATE * 98 / 1000
    threshold = options.vad_threshold
    neg_threshold = max(threshold - 0.15, 0.01)  # leaving speech needs a lower probability

    triggered = False
    speeches, current = [], {}
    temp_end = prev_end = next_start = 0
    possible_ends = []  # (silence start, silence length) candidates for a forced cut
    for index, probability in enumerate(probabilities.tolist()):
        sample = WINDOW * index
        # Speech is back after a pause: remember the pause as a possible cut point.
        if probability >= threshold and temp_end:
            silence = sample - temp_end
            if silence > min_silence_at_max_speech:
                possible_ends.append((temp_end, silence))
            temp_end = 0
            if next_start < prev_end:
                next_start = sample
        # Start of speech.
        if probability >= threshold and not triggered:
            triggered = True
            current["start"] = sample
            continue
        # Region too long: cut at the longest pause seen inside it.
        if triggered and sample - current["start"] > max_speech:
            if possible_ends:
                prev_end, length = max(possible_ends, key=lambda item: item[1])
                current["end"] = prev_end
                speeches.append(current)
                current = {}
                next_start = prev_end + length
                if next_start < prev_end + sample:
                    current["start"] = next_start
                else:
                    triggered = False
            else:
                current["end"] = sample
                speeches.append(current)
                current = {}
                triggered = False
            prev_end = next_start = temp_end = 0
            possible_ends = []
            if not triggered:
                continue
        # Silence while in speech: end the region once the pause is long enough.
        if probability < neg_threshold and triggered:
            if not temp_end:
                temp_end = sample
            if sample - temp_end < min_silence:
                continue
            current["end"] = temp_end
            if current["end"] - current["start"] > min_speech:
                speeches.append(current)
            current = {}
            prev_end = next_start = temp_end = 0
            triggered = False
            possible_ends = []
    if current and n_samples - current["start"] > min_speech:
        current["end"] = n_samples
        speeches.append(current)

    # Padding; neighbours closer than two paddings share the gap between them.
    for index, speech in enumerate(speeches):
        if index == 0:
            speech["start"] = int(max(0, speech["start"] - pad))
        if index != len(speeches) - 1:
            gap = speeches[index + 1]["start"] - speech["end"]
            if gap < 2 * pad:
                speech["end"] += int(gap // 2)
                speeches[index + 1]["start"] = int(max(0, speeches[index + 1]["start"] - gap // 2))
            else:
                speech["end"] = int(min(n_samples, speech["end"] + pad))
                speeches[index + 1]["start"] = int(max(0, speeches[index + 1]["start"] - pad))
        else:
            speech["end"] = int(min(n_samples, speech["end"] + pad))
    # Silero reports seconds rounded to 0.1 s (time_resolution=1). Keeping the
    # same rounding gives exactly the chunks, and so the text, of v0.1.
    total = n_samples / SAMPLE_RATE
    regions = []
    for speech in speeches:
        start = max(round(speech["start"] / SAMPLE_RATE, 1), 0)
        end = min(round(speech["end"] / SAMPLE_RATE, 1), total)
        regions.append((int(start * SAMPLE_RATE), int(end * SAMPLE_RATE)))
    return regions


def group_chunks(regions, options: VadOptions):
    """Pack consecutive speech regions into chunks no longer than max_duration.

    A chunk keeps the pauses between the regions it contains. A chunk longer
    than strict_limit_duration (possible when a single region is longer) is
    split into equal parts. Returns (start, end) sample indices.
    """
    max_len = options.max_duration * SAMPLE_RATE
    hard_limit = options.strict_limit_duration * SAMPLE_RATE
    min_len = options.new_chunk_threshold * SAMPLE_RATE
    chunks = []

    def emit(start, end):
        length = end - start
        if length <= hard_limit:
            chunks.append((start, end))
            return
        parts = int(length / hard_limit) + 1
        step = length / parts
        for part in range(parts):
            chunks.append((int(start + part * step), int(start + (part + 1) * step) if part < parts - 1 else end))

    if not regions:
        return chunks
    chunk_start, chunk_end = regions[0]
    for start, end in regions[1:]:
        if chunk_end - chunk_start > min_len and end - chunk_start > max_len:
            emit(chunk_start, chunk_end)
            chunk_start = start
        chunk_end = end
    if chunk_end - chunk_start > min_len:
        emit(chunk_start, chunk_end)
    return chunks
