"""Tests for scripts/generate-assets.py — the asset pipeline that derives
favicons, halftone portrait, and OG-banner from the source profile photo.
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = REPO_ROOT / "app" / "static"
SCRIPT = REPO_ROOT / "scripts" / "generate-assets.py"


def run_generator():
    """Invoke the generator with the canonical source path."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, f"generator failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    return result


def test_generator_script_exists():
    assert SCRIPT.exists(), f"missing: {SCRIPT}"
    assert SCRIPT.stat().st_mode & 0o100, "generator script not executable"
