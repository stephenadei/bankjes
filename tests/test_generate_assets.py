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


from PIL import Image


def test_silhouette_outputs():
    run_generator()
    png = STATIC_DIR / "silhouette.svg"
    assert png.exists(), "silhouette.svg not produced"
    svg = png.read_text()
    assert svg.startswith("<?xml") or svg.startswith("<svg"), "not an SVG"
    assert "#5b7a3f" in svg.lower(), "moss colour missing from silhouette.svg"

    raster = STATIC_DIR / "silhouette-1024.png"
    assert raster.exists()
    with Image.open(raster) as im:
        assert im.size == (1024, 1024), f"silhouette png size {im.size}"
        # Subject (moss) and background (cream) should both be present
        colours = im.convert("RGB").getcolors(maxcolors=10_000) or []
        flat = {c for _, c in colours}
        assert (91, 122, 63) in flat, "moss not found in silhouette png"
        assert (250, 247, 240) in flat, "cream not found in silhouette png"


def test_halftone_output():
    run_generator()
    png = STATIC_DIR / "portrait-halftone.png"
    assert png.exists()
    with Image.open(png) as im:
        assert im.size == (560, 560), f"halftone size {im.size}"
        colours = {c for _, c in (im.convert("RGB").getcolors(maxcolors=10_000) or [])}
        assert (91, 122, 63) in colours
        assert (250, 247, 240) in colours


def test_favicon_outputs():
    run_generator()
    f32 = STATIC_DIR / "favicon-32.png"
    apple = STATIC_DIR / "apple-touch-icon.png"
    assert f32.exists() and apple.exists()
    with Image.open(f32) as im:
        assert im.size == (32, 32)
    with Image.open(apple) as im:
        assert im.size == (180, 180)
        # Apple expects opaque; no alpha
        assert im.mode in ("RGB", "P"), f"apple-touch must be opaque, got {im.mode}"
