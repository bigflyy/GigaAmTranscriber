"""PyInstaller entry point for the console app (gigaam-cli.exe)."""

from gigaam_app.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
