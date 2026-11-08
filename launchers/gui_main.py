"""PyInstaller entry point for the windowed app (GigaAmTranscriber.exe)."""

import multiprocessing

from gigaam_app.paths import restore_child_environment
from gigaam_app.window import main

if __name__ == "__main__":
    # The models run in a second copy of this program (gigaam_app.worker.WorkerProcess);
    # in that copy freeze_support() runs the model process and never returns.
    multiprocessing.freeze_support()
    restore_child_environment()
    raise SystemExit(main())
