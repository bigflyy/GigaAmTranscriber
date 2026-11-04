import sys, time
sys.path.insert(0, r"C:\MyProjects\GigaAmTranscriber")
import torch, gigaam
from gigaam.vad_utils import segment_audio_file
device = sys.argv[2]
model = gigaam.load_model("v3_e2e_rnnt", device=device)
for run in (1, 2):
    t = time.perf_counter()
    torch.set_num_threads(1)
    segs, bnds = segment_audio_file(sys.argv[1], 16000)
    tv = time.perf_counter() - t
    torch.set_num_threads(8)
    enc = dec = 0.0
    with torch.inference_mode():
        for s in segs:
            wav = s.to(model._device).unsqueeze(0).to(model._dtype)
            ln = torch.full([1], wav.shape[-1], device=model._device)
            t1 = time.perf_counter(); e, el = model.forward(wav, ln)
            if device == "cuda": torch.cuda.synchronize()
            t2 = time.perf_counter(); model.decoding.decode(model.head, e, el)
            if device == "cuda": torch.cuda.synchronize()
            t3 = time.perf_counter(); enc += t2 - t1; dec += t3 - t2
    print(f"run{run}: VAD(+2x ffmpeg) {tv:.2f}s  encoder {enc:.2f}s  rnnt-decode {dec:.2f}s  chunks {len(segs)}", flush=True)
