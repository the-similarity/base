from __future__ import annotations

from pathlib import Path

import pandas as pd

from the_similarity_data.normalize import canonicalize_ohlcv_frame


def upsert_parquet(path: Path, frame: pd.DataFrame) -> pd.DataFrame:
    path.parent.mkdir(parents=True, exist_ok=True)

    canonical = canonicalize_ohlcv_frame(frame)
    if path.exists():
        existing = pd.read_parquet(path)
        canonical = pd.concat([existing, canonical], ignore_index=True)
        canonical = canonicalize_ohlcv_frame(canonical)

    canonical.to_parquet(path, index=False)
    return canonical
