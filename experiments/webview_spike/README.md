# pywebview spike (plan 02, A1-A2)

`spike.py` opens `page.html` in pywebview, calls Python from the page, pushes lines
from a Python thread with `evaluate_js`, registers a drop handler and writes timings
to a JSON file.

- Windows, off screen: `python run_offscreen.py OUT.png 3 -- python spike.py OUT.json --close-after 1 --offscreen`.
  The window sits at (-6000, -6000) and cannot take focus. A hidden desktop does not
  work: WebView2 does not paint there (white capture) and `evaluate_js` stalls.
- WSL Ubuntu: `bash linux_run.sh` (venv in `~/.venvs/gigaam-spike` with the system GTK,
  Xvfb, screenshot by `grab_x11.py`). It must unset `WAYLAND_DISPLAY` and set
  `GDK_BACKEND=x11`, or the window opens on the real screen through WSLg.
