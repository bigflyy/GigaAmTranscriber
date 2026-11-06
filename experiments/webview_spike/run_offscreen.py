"""Run the spike off screen on the normal desktop; save a PNG of its window via PrintWindow."""
import ctypes, subprocess, sys, time
sys.path.insert(0, r"C:\MyProjects\GigaAmTranscriber\tools")
import gui_smoke_test as smoke

png, shot_after = sys.argv[1], float(sys.argv[2])
command = sys.argv[sys.argv.index("--") + 1:]
started = time.perf_counter()
process = subprocess.Popen(command)
hwnd = None
while hwnd is None and time.perf_counter() - started < 60:
    hwnd = smoke.user32.FindWindowW(None, "GigaAM spike") or None
    time.sleep(0.05)
print(f"window found after {time.perf_counter() - started:.2f} s" if hwnd else "no window")
if hwnd:
    time.sleep(max(0.0, shot_after - (time.perf_counter() - started)))
    smoke.save_png(hwnd, png)
try:
    process.wait(60)
except subprocess.TimeoutExpired:
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True)
    print("killed")
print("exit", process.returncode)
