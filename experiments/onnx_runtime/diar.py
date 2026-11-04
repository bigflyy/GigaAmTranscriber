"""Measure sherpa-onnx speaker diarization speed and output on a real recording."""
import sys, time, collections
t0 = time.perf_counter()
import sherpa_onnx
from ortasr import decode_audio
D = sys.argv[2]
emb = sys.argv[3]
cfg = sherpa_onnx.OfflineSpeakerDiarizationConfig(
    segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
        pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
            model=D + "/sherpa-onnx-pyannote-segmentation-3-0/model.onnx"), num_threads=8),
    embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=D + "/" + emb, num_threads=8),
    clustering=sherpa_onnx.FastClusteringConfig(num_clusters=-1, threshold=float(sys.argv[4])),
    min_duration_on=0.3, min_duration_off=0.5)
sd = sherpa_onnx.OfflineSpeakerDiarization(cfg)
print("load", round(time.perf_counter() - t0, 2))
audio = decode_audio(sys.argv[1])
t = time.perf_counter()
segs = sd.process(audio).sort_by_start_time()
el = time.perf_counter() - t
dur = collections.Counter()
for s in segs: dur[s.speaker] += s.end - s.start
print(f"audio {len(audio)/16000:.0f}s diarized in {el:.1f}s ({len(audio)/16000/el:.0f}x rt); speakers: {len(dur)}",
      {k: round(v) for k, v in sorted(dur.items())})
for s in segs[:12]: print(f"  {s.start:7.1f}-{s.end:7.1f} spk{s.speaker}")
