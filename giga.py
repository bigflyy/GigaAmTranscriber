# qwen3-tts conda environment 
import gigaam
import torch

def format_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}" if hours > 0 else f"{minutes:02d}:{secs:06.3f}"

# Setup
device = 'cuda' if torch.cuda.is_available() else 'cpu'
audio_path = r"C:\Users\User\Downloads\research-2026.mp4"

# Load GigaAM (transcription)
print(f"🎙️ Loading GigaAM on {device}...")
model = gigaam.load_model("v3_e2e_rnnt", device=device)

# Run both
print("⏳ Processing audio...")
segments = model.transcribe_longform(audio_path)

# Align and print (simplified)
print("\n" + "="*70)
for i, seg in enumerate(segments, 1):
    start, end = seg['boundaries']
    # Simple midpoint matching (improve with overlap logic if needed)
    mid = (start + end) / 2
    print(f"[{format_time(start)} - {format_time(end)}] {seg['transcription']}")
print("="*70)