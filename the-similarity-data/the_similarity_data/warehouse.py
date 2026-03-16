"""DuckDB-based data warehouse for The Similarity.

Provides a unified SQL interface over the Hive-partitioned parquet files.
Supports:
  - Registering all parquet files as a single queryable view
  - Cross-asset SQL queries (e.g., "all assets above 50-day SMA")
  - Coverage stats, gap detection, freshness checks
  - Efficient columnar scans without loading everything into memory

Usage:
    from the_similarity_data.warehouse import Warehouse

    wh = Warehouse("/path/to/the-similarity-data")
    wh.register_all()

    # Query any asset
    df = wh.query("SELECT * FROM ohlcv WHERE symbol = 'btc_usdt' AND timeframe = '1d' LIMIT 10")

    # Coverage stats
    stats = wh.coverage()

    # Data quality
    issues = wh.check_quality()
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)


@dataclass
class CoverageStats:
    """Summary of data warehouse coverage."""
    total_datasets: int = 0
    total_rows: int = 0
    by_asset_class: dict[str, int] = field(default_factory=dict)
    by_timeframe: dict[str, int] = field(default_factory=dict)
    by_source: dict[str, int] = field(default_factory=dict)
    symbols: list[str] = field(default_factory=list)
    oldest_timestamp: str | None = None
    newest_timestamp: str | None = None


@dataclass
class QualityIssue:
    """A data quality problem detected in the warehouse."""
    dataset_id: str
    issue_type: str  # "gap", "stale", "empty", "duplicate", "spike"
    severity: str    # "warning", "error"
    message: str
    details: dict = field(default_factory=dict)


class Warehouse:
    """DuckDB-powered data warehouse over parquet files.

    The warehouse scans the data/ directory for parquet files matching
    the convention: data/{asset_class}/{symbol}/{timeframe}.parquet

    Each file is registered with metadata columns (asset_class, symbol,
    timeframe) injected automatically, creating a single unified view.
    """

    def __init__(self, data_root: str | Path, db_path: str = ":memory:"):
        self.data_root = Path(data_root)
        self.data_dir = self.data_root / "data"
        self.manifest_path = self.data_root / "manifests" / "catalog.json"
        self.con = duckdb.connect(db_path)
        self._registered = False

    def close(self) -> None:
        self.con.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def register_all(self) -> int:
        """Scan data/ and register all parquet files into a unified ohlcv view.

        Returns the number of datasets registered.
        """
        parquet_files = sorted(self.data_dir.rglob("*.parquet"))
        if not parquet_files:
            logger.warning("no parquet files found in %s", self.data_dir)
            self._registered = True
            self.con.execute("CREATE OR REPLACE VIEW ohlcv AS SELECT * FROM (SELECT 1) WHERE false")
            return 0

        # Build a UNION ALL over all parquet files with metadata columns
        union_parts = []
        count = 0
        for pf in parquet_files:
            rel = pf.relative_to(self.data_dir)
            parts = rel.parts  # e.g., ('crypto', 'btc_usdt', '1d.parquet')
            if len(parts) != 3:
                logger.warning("skipping unexpected path: %s", pf)
                continue

            asset_class = parts[0]
            symbol = parts[1]
            timeframe = parts[2].replace(".parquet", "")

            union_parts.append(
                f"SELECT *, '{asset_class}' AS asset_class, "
                f"'{symbol}' AS symbol, '{timeframe}' AS timeframe "
                f"FROM read_parquet('{pf}')"
            )
            count += 1

        if not union_parts:
            self._registered = True
            return 0

        view_sql = " UNION ALL ".join(union_parts)
        self.con.execute(f"CREATE OR REPLACE VIEW ohlcv AS {view_sql}")
        self._registered = True
        logger.info("registered %d datasets into ohlcv view", count)
        return count

    def register_dataset(
        self,
        asset_class: str,
        symbol: str,
        timeframe: str,
    ) -> bool:
        """Register a single dataset as a named table.

        Useful for targeted queries without scanning all files.
        """
        path = self.data_dir / asset_class / symbol / f"{timeframe}.parquet"
        if not path.exists():
            return False

        table_name = f"{asset_class}_{symbol}_{timeframe}"
        self.con.execute(
            f"CREATE OR REPLACE TABLE {table_name} AS "
            f"SELECT *, '{asset_class}' AS asset_class, "
            f"'{symbol}' AS symbol, '{timeframe}' AS timeframe "
            f"FROM read_parquet('{path}')"
        )
        return True

    def query(self, sql: str) -> list[dict]:
        """Execute SQL and return results as list of dicts."""
        result = self.con.execute(sql)
        columns = [desc[0] for desc in result.description]
        return [dict(zip(columns, row)) for row in result.fetchall()]

    def query_df(self, sql: str):
        """Execute SQL and return as pandas DataFrame."""
        return self.con.execute(sql).fetchdf()

    def query_arrow(self, sql: str):
        """Execute SQL and return as PyArrow Table (zero-copy)."""
        return self.con.execute(sql).fetch_arrow_table()

    def coverage(self) -> CoverageStats:
        """Compute coverage statistics from the manifest."""
        if not self.manifest_path.exists():
            return CoverageStats()

        catalog = json.loads(self.manifest_path.read_text())
        datasets = catalog.get("datasets", [])

        stats = CoverageStats(total_datasets=len(datasets))
        symbols = set()
        oldest = None
        newest = None

        for ds in datasets:
            ac = ds.get("asset_class", "unknown")
            tf = ds.get("timeframe", "unknown")
            src = ds.get("source", "unknown")

            stats.by_asset_class[ac] = stats.by_asset_class.get(ac, 0) + 1
            stats.by_timeframe[tf] = stats.by_timeframe.get(tf, 0) + 1
            stats.by_source[src] = stats.by_source.get(src, 0) + 1
            stats.total_rows += ds.get("row_count", 0)
            symbols.add(f"{ac}/{ds.get('symbol', '')}")

            start = ds.get("start_timestamp")
            end = ds.get("end_timestamp")
            if start and (oldest is None or start < oldest):
                oldest = start
            if end and (newest is None or end > newest):
                newest = end

        stats.symbols = sorted(symbols)
        stats.oldest_timestamp = oldest
        stats.newest_timestamp = newest
        return stats

    def coverage_from_parquet(self) -> CoverageStats:
        """Compute coverage by scanning actual parquet files (slower but accurate)."""
        if not self._registered:
            self.register_all()

        try:
            result = self.con.execute("""
                SELECT
                    asset_class,
                    symbol,
                    timeframe,
                    COUNT(*) as row_count,
                    MIN(timestamp) as min_ts,
                    MAX(timestamp) as max_ts
                FROM ohlcv
                GROUP BY asset_class, symbol, timeframe
                ORDER BY asset_class, symbol, timeframe
            """).fetchall()
        except duckdb.CatalogException:
            return CoverageStats()

        stats = CoverageStats()
        symbols = set()
        for row in result:
            ac, sym, tf, count, min_ts, max_ts = row
            stats.total_datasets += 1
            stats.total_rows += count
            stats.by_asset_class[ac] = stats.by_asset_class.get(ac, 0) + 1
            stats.by_timeframe[tf] = stats.by_timeframe.get(tf, 0) + 1
            symbols.add(f"{ac}/{sym}")

            min_str = str(min_ts) if min_ts else None
            max_str = str(max_ts) if max_ts else None
            if min_str and (stats.oldest_timestamp is None or min_str < stats.oldest_timestamp):
                stats.oldest_timestamp = min_str
            if max_str and (stats.newest_timestamp is None or max_str > stats.newest_timestamp):
                stats.newest_timestamp = max_str

        stats.symbols = sorted(symbols)
        return stats

    def check_quality(self, max_gap_multiplier: float = 3.0, stale_hours: float = 48.0) -> list[QualityIssue]:
        """Run data quality checks across all datasets.

        Checks:
          1. Empty datasets (no rows)
          2. Stale data (last timestamp > stale_hours ago)
          3. Gaps (missing bars > max_gap_multiplier * expected interval)
          4. Duplicate timestamps
          5. Price spikes (>50% single-bar move)
        """
        issues: list[QualityIssue] = []

        if not self.manifest_path.exists():
            return issues

        catalog = json.loads(self.manifest_path.read_text())
        now = datetime.now(UTC)

        tf_seconds = {
            "1m": 60, "5m": 300, "15m": 900, "1h": 3600,
            "4h": 14400, "1d": 86400,
        }

        for ds in catalog.get("datasets", []):
            dataset_id = f"{ds['asset_class']}/{ds['symbol']}/{ds['timeframe']}"
            path = self.data_root / ds.get("path", "")

            # Check 1: Empty
            row_count = ds.get("row_count", 0)
            if row_count == 0:
                issues.append(QualityIssue(
                    dataset_id=dataset_id,
                    issue_type="empty",
                    severity="error",
                    message=f"dataset has 0 rows",
                ))
                continue

            # Check 2: Stale
            last_updated = ds.get("last_updated_at")
            if last_updated:
                try:
                    updated_dt = datetime.fromisoformat(last_updated)
                    hours_since = (now - updated_dt).total_seconds() / 3600
                    if hours_since > stale_hours:
                        issues.append(QualityIssue(
                            dataset_id=dataset_id,
                            issue_type="stale",
                            severity="warning",
                            message=f"last updated {hours_since:.0f}h ago (threshold: {stale_hours}h)",
                            details={"hours_since_update": round(hours_since, 1)},
                        ))
                except (ValueError, TypeError):
                    pass

            # Checks 3-5 require reading the parquet file
            if not path.exists():
                issues.append(QualityIssue(
                    dataset_id=dataset_id,
                    issue_type="missing_file",
                    severity="error",
                    message=f"parquet file not found: {path}",
                ))
                continue

            tf = ds.get("timeframe", "1d")
            expected_interval = tf_seconds.get(tf, 86400)

            try:
                result = self.con.execute(f"""
                    WITH ts AS (
                        SELECT timestamp,
                               close,
                               LAG(timestamp) OVER (ORDER BY timestamp) as prev_ts,
                               LAG(close) OVER (ORDER BY timestamp) as prev_close
                        FROM read_parquet('{path}')
                        ORDER BY timestamp
                    )
                    SELECT
                        COUNT(*) FILTER (
                            WHERE EPOCH(timestamp - prev_ts) > {expected_interval * max_gap_multiplier}
                        ) as gap_count,
                        MAX(EPOCH(timestamp - prev_ts)) as max_gap_seconds,
                        COUNT(*) FILTER (
                            WHERE prev_close > 0
                            AND ABS(close - prev_close) / prev_close > 0.5
                        ) as spike_count
                    FROM ts
                    WHERE prev_ts IS NOT NULL
                """).fetchone()

                if result:
                    gap_count, max_gap, spike_count = result

                    if gap_count and gap_count > 0:
                        issues.append(QualityIssue(
                            dataset_id=dataset_id,
                            issue_type="gap",
                            severity="warning",
                            message=f"{gap_count} gaps exceeding {max_gap_multiplier}x expected interval",
                            details={
                                "gap_count": gap_count,
                                "max_gap_seconds": max_gap,
                                "expected_interval": expected_interval,
                            },
                        ))

                    if spike_count and spike_count > 0:
                        issues.append(QualityIssue(
                            dataset_id=dataset_id,
                            issue_type="spike",
                            severity="warning",
                            message=f"{spike_count} price spikes >50% in single bar",
                            details={"spike_count": spike_count},
                        ))

                # Check duplicates
                dup_result = self.con.execute(f"""
                    SELECT COUNT(*) - COUNT(DISTINCT timestamp)
                    FROM read_parquet('{path}')
                """).fetchone()

                if dup_result and dup_result[0] > 0:
                    issues.append(QualityIssue(
                        dataset_id=dataset_id,
                        issue_type="duplicate",
                        severity="warning",
                        message=f"{dup_result[0]} duplicate timestamps",
                        details={"duplicate_count": dup_result[0]},
                    ))

            except Exception as exc:
                issues.append(QualityIssue(
                    dataset_id=dataset_id,
                    issue_type="read_error",
                    severity="error",
                    message=f"failed to read parquet: {exc}",
                ))

        return issues

    def freshness_report(self) -> list[dict]:
        """Return freshness info for each dataset, sorted by staleness."""
        if not self.manifest_path.exists():
            return []

        catalog = json.loads(self.manifest_path.read_text())
        now = datetime.now(UTC)
        report = []

        for ds in catalog.get("datasets", []):
            last_updated = ds.get("last_updated_at")
            hours_since = None
            if last_updated:
                try:
                    updated_dt = datetime.fromisoformat(last_updated)
                    hours_since = (now - updated_dt).total_seconds() / 3600
                except (ValueError, TypeError):
                    pass

            report.append({
                "dataset_id": f"{ds['asset_class']}/{ds['symbol']}/{ds['timeframe']}",
                "source": ds.get("source"),
                "row_count": ds.get("row_count", 0),
                "start": ds.get("start_timestamp"),
                "end": ds.get("end_timestamp"),
                "last_updated": last_updated,
                "hours_since_update": round(hours_since, 1) if hours_since else None,
                "is_stale": hours_since is not None and hours_since > 48,
            })

        report.sort(key=lambda r: r.get("hours_since_update") or 0, reverse=True)
        return report

    def search_assets(
        self,
        asset_class: str | None = None,
        source: str | None = None,
        min_rows: int = 0,
    ) -> list[dict]:
        """Search the catalog for assets matching filters."""
        if not self.manifest_path.exists():
            return []

        catalog = json.loads(self.manifest_path.read_text())
        results = []
        for ds in catalog.get("datasets", []):
            if asset_class and ds.get("asset_class") != asset_class:
                continue
            if source and ds.get("source") != source:
                continue
            if ds.get("row_count", 0) < min_rows:
                continue
            results.append(ds)
        return results

    def cross_asset_query(self, symbols: list[str], timeframe: str = "1d", column: str = "close") -> dict:
        """Load close prices for multiple symbols aligned by timestamp.

        Returns {symbol: [(timestamp, value), ...]} for cross-correlation analysis.
        """
        if not self._registered:
            self.register_all()

        result = {}
        for sym in symbols:
            try:
                rows = self.con.execute(f"""
                    SELECT timestamp, {column}
                    FROM ohlcv
                    WHERE symbol = '{sym}' AND timeframe = '{timeframe}'
                    ORDER BY timestamp
                """).fetchall()
                result[sym] = [(str(r[0]), r[1]) for r in rows]
            except Exception:
                result[sym] = []
        return result
