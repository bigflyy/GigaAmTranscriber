"""PyInstaller entry point for the windowed app (GigaAmTranscriber.exe)."""

from gigaam_app.gui import main

if __name__ == "__main__":
    raise SystemExit(main())
