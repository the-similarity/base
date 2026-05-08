import { NextResponse } from "next/server";
import { execFile as execFileCallback } from "node:child_process";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { promisify } from "node:util";
import {
  GHOST5_DEFAULT_DATASET_ID,
  GHOST5_DEFAULT_HORIZON,
  GHOST5_DEFAULT_LENGTH,
  GHOST5_TOP_K,
  createGhost5ScanFromSeries,
  datasetId,
  type Ghost5Dataset,
  type Ghost5Point,
} from "../../../lib/ghost5";

export const revalidate = 0;

const execFile = promisify(execFileCallback);
const REPO_ROOT = resolve(process.cwd(), "..");
const DATA_ROOT = resolve(REPO_ROOT, "the-similarity-data");
const MANIFEST_PATH = resolve(DATA_ROOT, "manifests", "catalog.json");
const MAX_PARQUET_BARS = 20_000;

type ManifestItem = {
  asset_class: string;
  symbol: string;
  timeframe: string;
  source?: string;
  path: string;
  row_count?: number;
  start_timestamp?: string | null;
  end_timestamp?: string | null;
  last_updated_at?: string | null;
};

function readNumber(params: URLSearchParams, key: string, fallback: number): number {
  const value = params.get(key);
  if (value === null) return fallback;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function readOptionalNumber(params: URLSearchParams, key: string): number | undefined {
  const value = params.get(key);
  if (value === null) return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function toDataset(item: ManifestItem): Ghost5Dataset {
  const dataset: Ghost5Dataset = {
    id: `${item.asset_class}/${item.symbol}/${item.timeframe}`,
    label: `${item.symbol.toUpperCase()} ${item.timeframe}`,
    assetClass: item.asset_class,
    symbol: item.symbol,
    timeframe: item.timeframe,
    source: item.source ?? "unknown",
    path: item.path,
    rowCount: item.row_count ?? 0,
    startTimestamp: item.start_timestamp ?? null,
    endTimestamp: item.end_timestamp ?? null,
    lastUpdatedAt: item.last_updated_at ?? null,
  };
  return { ...dataset, id: datasetId(dataset) };
}

async function loadCatalog(): Promise<Ghost5Dataset[]> {
  const manifest = JSON.parse(await readFile(MANIFEST_PATH, "utf8")) as {
    datasets?: ManifestItem[];
  };
  const byId = new Map<string, Ghost5Dataset>();
  for (const item of manifest.datasets ?? []) {
    const dataset = toDataset(item);
    const existing = byId.get(dataset.id);
    if (!existing || dataset.source === "twelvedata") {
      byId.set(dataset.id, dataset);
    }
  }

  return [...byId.values()].sort((a, b) => {
    const asset = a.assetClass.localeCompare(b.assetClass);
    if (asset !== 0) return asset;
    const symbol = a.symbol.localeCompare(b.symbol);
    if (symbol !== 0) return symbol;
    return a.timeframe.localeCompare(b.timeframe);
  });
}

async function readParquetSeries(dataset: Ghost5Dataset): Promise<Ghost5Point[]> {
  const parquetPath = resolve(DATA_ROOT, dataset.path);
  const script = [
    "import json, sys",
    "import pandas as pd",
    "df = pd.read_parquet(sys.argv[1])",
    "df = df.sort_values('timestamp').tail(int(sys.argv[2])).reset_index(drop=True)",
    "rows = []",
    "for i, row in df.iterrows():",
    "    close = row.get('close')",
    "    if pd.isna(close):",
    "        continue",
    "    ts = row.get('timestamp')",
    "    rows.append({",
    "        'index': int(i),",
    "        'date': pd.Timestamp(ts).isoformat(),",
    "        'value': float(close),",
    "        'open': None if pd.isna(row.get('open')) else float(row.get('open')),",
    "        'high': None if pd.isna(row.get('high')) else float(row.get('high')),",
    "        'low': None if pd.isna(row.get('low')) else float(row.get('low')),",
    "        'volume': None if pd.isna(row.get('volume')) else float(row.get('volume')),",
    "    })",
    "print(json.dumps(rows, separators=(',', ':')))",
  ].join("\n");

  const { stdout } = await execFile("python", ["-c", script, parquetPath, String(MAX_PARQUET_BARS)], {
    cwd: REPO_ROOT,
    timeout: 15_000,
    maxBuffer: 24 * 1024 * 1024,
  });
  return JSON.parse(stdout) as Ghost5Point[];
}

function selectDataset(catalog: Ghost5Dataset[], requested: string | null): Ghost5Dataset {
  return (
    catalog.find((item) => item.id === requested) ??
    catalog.find((item) => item.id === GHOST5_DEFAULT_DATASET_ID) ??
    catalog[0]
  );
}

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const catalog = await loadCatalog();
    if (catalog.length === 0) {
      return NextResponse.json(
        { error: "Ghost5 catalog is empty." },
        { status: 503 },
      );
    }

    const dataset = selectDataset(catalog, url.searchParams.get("dataset"));
    const series = await readParquetSeries(dataset);
    const scan = createGhost5ScanFromSeries({
      dataset,
      catalog,
      series,
      start: readOptionalNumber(url.searchParams, "start"),
      length: readNumber(url.searchParams, "length", GHOST5_DEFAULT_LENGTH),
      horizon: readNumber(url.searchParams, "horizon", GHOST5_DEFAULT_HORIZON),
      topK: readNumber(url.searchParams, "topK", GHOST5_TOP_K),
      entryOffset: readOptionalNumber(url.searchParams, "entryOffset"),
      takeProfitPct: readOptionalNumber(url.searchParams, "takeProfitPct"),
      stopLossPct: readOptionalNumber(url.searchParams, "stopLossPct"),
    });

    return NextResponse.json(scan, {
      headers: {
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Ghost5 scan failed.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
