#!/bin/bash
# Set up a venv with pywebview (GTK from the system) and run the spike under Xvfb.
set -e
cd "$(dirname "$0")"
V=~/.venvs/gigaam-spike
if [ ! -x "$V/bin/python" ]; then python3 -m venv --system-site-packages "$V"; fi
"$V/bin/pip" -q install pywebview 2>&1 | tail -2
"$V/bin/python" -c "import webview; print('pywebview ok')"
rm -f lin.json lin.png
unset WAYLAND_DISPLAY; export GDK_BACKEND=x11
xvfb-run -a -s "-screen 0 1100x720x24" bash -c "
  \"$V/bin/python\" spike.py lin.json --close-after 4 &
  sleep 3.5; python3 grab_x11.py lin.png; wait"
cat lin.json
