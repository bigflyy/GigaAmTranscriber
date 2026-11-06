"""PyInstaller entry point for the console app (gigaam-cli.exe)."""

from gigaam_app.paths import restore_child_environment
from gigaam_app.cli import main

if __name__ == "__main__":
    restore_child_environment()
    raise SystemExit(main())
