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
import sys
from pathlib import Path

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
    # Generators wired up in later tasks.
    return 0


if __name__ == "__main__":
    sys.exit(main())
