#!/usr/bin/env python3
"""Run the full OpenClaw-first interpretation cycle, then generate signals."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).parent


def run_step(args: list[str]) -> None:
    result = subprocess.run(
        args,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip())
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> int:
    run_step(["python3", "run.py", "openclaw_export"])
    run_step(["python3", "run.py", "openclaw_prepare"])
    run_step(["python3", "openclaw_run.py"])
    run_step(["python3", "run.py", "signal_scan"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
