import sys, time
T0 = time.perf_counter()
def mark(label, t=[T0]):
    now = time.perf_counter(); print(f"{label:<28} {now-t[0]:7.2f}s  (cum {now-T0:6.2f})", flush=True); t[0] = now
device = sys.argv[2]
sys.path.insert(0, r"C:\MyProjects\GigaAmTranscriber")
import torch; mark("import torch")
ok = torch.cuda.is_available(); mark(f"cuda.is_available={ok}")
import gigaam; mark("import gigaam (hydra...)")
from gigaam import hash_path
p = gigaam._CACHE_DIR + "/v3_e2e_rnnt.ckpt"
hash_path(p); mark("md5 of 449MB ckpt")
model = gigaam.load_model("v3_e2e_rnnt", device=device)
if device == "cuda": torch.cuda.synchronize()
mark("load_model (md5 again+load)")
from gigaam import vad_utils; mark("import silero_vad")
from gigaam.preprocess import load_audio
a = load_audio(sys.argv[1]); mark(f"ffmpeg decode {a.numel()/16000:.0f}s")
seg = model.transcribe_longform(sys.argv[1], cpu_threads=8)
if device == "cuda": torch.cuda.synchronize()
mark(f"transcribe_longform ({len(seg)} chunks)")
seg = model.transcribe_longform(sys.argv[1], cpu_threads=8, vad_progress_callback=None)
mark("transcribe_longform 2nd")
