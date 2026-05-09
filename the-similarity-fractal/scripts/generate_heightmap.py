#!/usr/bin/env python3
"""Generate a JSON heightmap usable by the headless JS worlds runner.

Output schema (JSON):
    {
        "type": "heightmap",
        "version": 1,
        "width": <int>,                # grid columns (X axis)
        "height": <int>,               # grid rows (Y axis)
        "size": <int>,                 # convenience alias when width == height
        "preset": <str>,               # terrain preset name (e.g. "alpine")
        "seed": <int>,                 # RNG seed used
        "z_range": [zmin, zmax],       # min/max of the raw float values
        "data": [<float>, <float>, ...] # length == width * height,
                                        # row-major: data[y * width + x]
    }

The exported `data` array carries the raw, unscaled float heights from
``the_similarity.core.terrain_generator.TerrainGenerator``. Values are
already approximately in [0, 1] but the JS sim may renormalize / scale
to a desired vertical exaggeration before consuming them.

Usage::

    python the-similarity-fractal/scripts/generate_heightmap.py \\
        --size 64 --seed 7 --preset alpine \\
        --out the-similarity-fractal/data/heightmap_default.json

Why JSON (not binary)?
- The headless runner is pure-Node with no extra deps; ``JSON.parse`` is
  built in and the file size for 64x64 floats is < 100 KB.
- Human-inspectable so debugging "is the heightmap actually loaded?" is
  one ``head -c 200`` away.

This is a *one-shot* script: re-run it whenever a new preset / seed is
desired. The output file is checked into git so JS tests have a stable
fixture without having to call into Python.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


# Add repo root to sys.path so this script works when invoked from any cwd.
# We resolve to the repo root by walking up from this file's location.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Import after path manipulation so the `the_similarity` package resolves.
from the_similarity.core.terrain_generator import TerrainGenerator  # noqa: E402


def main() -> int:
    """CLI entrypoint — parse args, generate, write JSON, return exit code."""
    parser = argparse.ArgumentParser(
        description="Export a heightmap JSON for the headless worlds runner."
    )
    parser.add_argument(
        "--size",
        type=int,
        default=64,
        help="Heightmap is size x size (default: 64).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="RNG seed (default: 42).",
    )
    parser.add_argument(
        "--preset",
        type=str,
        default="alpine",
        help="Terrain preset name passed to TerrainGenerator (default: alpine).",
    )
    parser.add_argument(
        "--out",
        type=str,
        required=True,
        help="Output JSON path. Parent dirs are created if missing.",
    )
    args = parser.parse_args()

    # Generate. The terrain pipeline already returns a normalized float64
    # heightmap of shape (size, size). We round-trip through Python lists
    # rather than numpy `.tolist()` arrays so the JSON has flat floats
    # (no nested lists of lists, no numpy quirks).
    gen = TerrainGenerator(args.preset)
    terrain = gen.generate(size=args.size, seed=args.seed)
    h = terrain.heightmap

    # Row-major flatten: data[y * width + x]. heightmap.shape is (rows, cols);
    # we treat rows as Y and cols as X to match the JS sim's (x, y) convention.
    width = h.shape[1]
    height = h.shape[0]
    flat = [float(v) for v in h.flatten(order="C")]

    payload = {
        "type": "heightmap",
        "version": 1,
        "width": width,
        "height": height,
        "size": width if width == height else None,
        "preset": args.preset,
        "seed": args.seed,
        "z_range": [float(h.min()), float(h.max())],
        "data": flat,
    }

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Pretty-print with separators tuned to keep the array compact while
    # leaving meta fields readable. The trailing newline keeps git diffs
    # clean.
    with out_path.open("w", encoding="utf-8") as f:
        # Use a custom separator for the data array to keep it on one line
        # so the file is compact. The metadata stays on individual lines.
        json.dump(payload, f, indent=2, separators=(",", ": "))
        f.write("\n")

    print(
        f"[heightmap] wrote {out_path} "
        f"({width}x{height}, preset={args.preset}, seed={args.seed}, "
        f"bytes={os.path.getsize(out_path)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
