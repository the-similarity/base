from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from the_similarity_data.config import load_dataset_specs
from the_similarity_data.refresh import refresh_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description="Run The Similarity data refresh on a fixed schedule")
    parser.add_argument("--interval-minutes", type=int, default=60)
    parser.add_argument("--asset-class", default=None)
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--timeframe", default=None)
    args = parser.parse_args()

    specs = load_dataset_specs()

    while True:
        started = datetime.now(UTC).isoformat()
        print(f"[{started}] refresh cycle started")
        refreshed = 0
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
                refresh_dataset(spec)
                refreshed += 1
            except Exception as error:
                print(
                    f"[{started}] refresh failed for {spec.asset_class}/{spec.symbol}/{spec.timeframe}: {error}",
                    file=sys.stderr,
                )

        print(f"[{started}] refreshed {refreshed} datasets")

        time.sleep(args.interval_minutes * 60)


if __name__ == "__main__":
    raise SystemExit(main())
