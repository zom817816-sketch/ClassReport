"""Entry point packaged for teachers: sync Feishu then generate all reports."""

from __future__ import annotations

import sys
from pathlib import Path

from classreport.cli import main


def application_root() -> Path:
    """Keep .env, data and output beside the executable in a PyInstaller build."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def teacher_args() -> list[str]:
    args = sys.argv[1:]
    if "--root" not in args:
        args.extend(["--root", str(application_root())])
    if "--sync-feishu" not in args:
        args.append("--sync-feishu")
    return args


if __name__ == "__main__":
    sys.argv = [sys.argv[0], *teacher_args()]
    main()
