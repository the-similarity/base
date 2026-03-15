from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from the_similarity_data.config import load_dataset_specs
from the_similarity_data.refresh import refresh_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh The Similarity parquet bank")
    parser.add_argument("--asset-class", default=None)
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--timeframe", default=None)
    args = parser.parse_args()

    specs = load_dataset_specs()
    results = []
    failures = 0
    for spec in specs:
        if not spec.enabled:
            continue
        if args.asset_class is not None and spec.asset_class != args.asset_class:
            continue
        if args.symbol is not None and spec.symbol != args.symbol:
            continue
        if args.timeframe is not None and spec.timeframe != args.timeframe:
            continue

        try:
            results.append(refresh_dataset(spec))
        except Exception as error:
            failures += 1
            print(
                f"refresh failed for {spec.asset_class}/{spec.symbol}/{spec.timeframe}: {error}",
                file=sys.stderr,
            )

    for result in results:
        print(
            f"{result.asset_class}/{result.symbol}/{result.timeframe} "
            f"rows={result.row_count} "
            f"start={result.start_timestamp} "
            f"end={result.end_timestamp} "
            f"path={result.path.as_posix()}"
        )

    total = len(results) + failures
    if total == 0:
        print("No datasets matched filters.", file=sys.stderr)
        return 1
    if failures:
        print(
            f"\n{len(results)}/{total} succeeded, {failures} failed.",
            file=sys.stderr,
        )
    # Exit 0 if at least half succeeded (partial refresh is better than none)
    return 1 if failures > len(results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
