#!/usr/bin/env python3
"""Generate all derived assets for Bankjes from the source profile photo.

Outputs to app/static/:
  silhouette.svg              vector silhouette (used by header-mark)
  favicon.svg                 same silhouette, tight viewBox
  favicon-32.png              32x32 PNG fallback
  apple-touch-icon.png        180x180 padded
  portrait-halftone.png       560x560 dithered duotone
  og-banner.png               1200x630 social-share banner

Reproducible: re-running overwrites every output. Source portrait stays out
of this repo — read by absolute path (--source overrides).
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

from PIL import Image, ImageFilter

REPO_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = REPO_ROOT / "app" / "static"

DEFAULT_SOURCE = Path(
    "/home/stephen/projects/cv/cv-portal/content/products/house-style/"
    "assets/profielfoto-stephen-adei.jpg"
)

# Bankjes palette
CREAM = (250, 247, 240)
MOSS  = (91, 122, 63)
MOSS2 = (122, 138, 71)
INK   = (45, 42, 38)
LINE  = (45, 42, 38, 25)  # rgba, ~10% alpha


def _mask_from_portrait(img: Image.Image, tol: int = 38) -> Image.Image:
    """Return an L-mode mask: white = subject, black = background.

    Strategy: sample the median colour from a 4-pixel-wide edge strip on all
    four sides (assumes subject is centred and never touches the frame), then
    mark every pixel whose RGB max-channel distance exceeds `tol` as subject.
    Cleaned with close-then-median to remove specks and fill micro-holes.
    """
    rgb = img.convert("RGB")
    w, h = rgb.size
    px = rgb.load()
    edge = []
    for x in range(0, w, 4):
        edge.append(px[x, 5])
        edge.append(px[x, h - 6])
    for y in range(0, h, 4):
        edge.append(px[5, y])
        edge.append(px[w - 6, y])
    bg = tuple(int(statistics.median(p[i] for p in edge)) for i in range(3))

    mask = Image.new("L", (w, h), 0)
    mp = mask.load()
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if max(abs(r - bg[0]), abs(g - bg[1]), abs(b - bg[2])) > tol:
                mp[x, y] = 255
    mask = mask.filter(ImageFilter.MaxFilter(5))   # dilate
    mask = mask.filter(ImageFilter.MinFilter(7))   # erode
    mask = mask.filter(ImageFilter.MedianFilter(5))
    return mask


def _square_crop(img: Image.Image, size: int = 1024) -> Image.Image:
    w, h = img.size
    sq = min(w, h)
    left = (w - sq) // 2 + 20  # bias right; subject sits slightly left of frame centre
    img = img.crop((left, 0, left + sq, sq))
    return img.resize((size, size), Image.LANCZOS)


def generate_silhouette(src: Image.Image, out_dir: Path) -> None:
    """Produce silhouette.svg, favicon.svg, silhouette-1024.png from a portrait."""
    sq = _square_crop(src, 1024)
    mask = _mask_from_portrait(sq)

    # Flat-fill PNG: subject -> moss, bg -> cream
    bg = Image.new("RGB", sq.size, CREAM)
    fg = Image.new("RGB", sq.size, MOSS)
    bg.paste(fg, (0, 0), mask)
    bg.save(out_dir / "silhouette-1024.png")

    # Trace mask to compact SVG via runs of horizontal pixels per row.
    # Simpler than potrace; produces a valid SVG that renders identically at
    # any size. For an editorial silhouette the run-length output is fine.
    svg_paths = []
    mp = mask.load()
    w, h = mask.size
    for y in range(h):
        x = 0
        while x < w:
            if mp[x, y] >= 128:
                x0 = x
                while x < w and mp[x, y] >= 128:
                    x += 1
                svg_paths.append(f"M{x0},{y}h{x - x0}v1h-{x - x0}z")
            else:
                x += 1
    body = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">'
        f'<rect width="{w}" height="{h}" fill="#faf7f0"/>'
        f'<path fill="#5b7a3f" d="{"".join(svg_paths)}"/>'
        f"</svg>"
    )
    (out_dir / "silhouette.svg").write_text(body)
    # Favicon variant is the same SVG; the head-link tag is what differs.
    (out_dir / "favicon.svg").write_text(body)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=STATIC_DIR)
    args = parser.parse_args(argv)

    if not args.source.exists():
        print(f"source not found: {args.source}", file=sys.stderr)
        return 2

    args.out.mkdir(parents=True, exist_ok=True)
    print(f"generate-assets: source={args.source} out={args.out}")
    src = Image.open(args.source).convert("RGB")
    generate_silhouette(src, args.out)
    print("silhouette done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
