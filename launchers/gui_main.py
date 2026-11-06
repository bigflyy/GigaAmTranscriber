"""PyInstaller entry point for the windowed app (GigaAmTranscriber.exe)."""

from gigaam_app.paths import restore_child_environment
from gigaam_app.window import main

if __name__ == "__main__":
    restore_child_environment()
    raise SystemExit(main())
