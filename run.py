#!/usr/bin/env python3
"""Run main.py with the project venv (uv) so deps are always found."""
import subprocess
import sys
from pathlib import Path

project_dir = Path(__file__).resolve().parent
result = subprocess.run(["uv", "run", "python", "main.py"], cwd=project_dir)
if result.returncode != 0:
    print("If 'uv' not found: brew install uv, then run: uv run python main.py", file=sys.stderr)
sys.exit(result.returncode)
