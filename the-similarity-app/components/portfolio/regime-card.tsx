"use client";

import React from "react";

export interface AssetRegime {
  name: string;
  ticker: string;
  regime: "trending_up" | "trending_down" | "mean_reverting" | "high_vol" | "low_vol";
  volatility: number;
  slope: number;
  hurst: number;
}

const regimeConfig: Record<
  AssetRegime["regime"],
  { label: string; color: string; dimColor: string }
> = {
  // Editorial deck semantics: only positive/negative ink gets hue; volatility
  // regimes use the monochrome ramp (text-primary → muted) to avoid hue noise.
  trending_up: { label: "Trending Up", color: "var(--positive)", dimColor: "var(--positive-dim)" },
  trending_down: { label: "Trending Down", color: "var(--negative)", dimColor: "var(--negative-dim)" },
  mean_reverting: { label: "Mean Reverting", color: "var(--accent)", dimColor: "var(--accent-dim)" },
  high_vol: { label: "High Vol", color: "var(--text-primary)", dimColor: "var(--bg-inset)" },
  low_vol: { label: "Low Vol", color: "var(--text-muted)", dimColor: "var(--bg-inset)" },
};

export function RegimeCard({ asset }: { asset: AssetRegime }) {
  const cfg = regimeConfig[asset.regime];

  return (
    <div className="portfolio-regime-card">
      <div className="portfolio-regime-card__header">
        <span className="portfolio-regime-card__ticker">{asset.ticker}</span>
        <span className="portfolio-regime-card__name">{asset.name}</span>
      </div>
      <div
        className="portfolio-regime-badge"
        style={{
          borderColor: cfg.color,
          background: cfg.dimColor,
          color: cfg.color,
        }}
      >
        <span
          className="portfolio-regime-badge__dot"
          style={{ background: cfg.color }}
        />
        {cfg.label}
      </div>
      <div className="portfolio-regime-card__stats">
        <div className="portfolio-regime-card__stat">
          <span className="portfolio-regime-card__stat-label">VOL</span>
          <span className="portfolio-regime-card__stat-value">
            {(asset.volatility * 100).toFixed(1)}%
          </span>
        </div>
        <div className="portfolio-regime-card__stat">
          <span className="portfolio-regime-card__stat-label">SLOPE</span>
          <span
            className="portfolio-regime-card__stat-value"
            style={{
              color: asset.slope >= 0 ? "var(--positive)" : "var(--negative)",
            }}
          >
            {asset.slope >= 0 ? "+" : ""}
            {asset.slope.toFixed(3)}
          </span>
        </div>
        <div className="portfolio-regime-card__stat">
          <span className="portfolio-regime-card__stat-label">HURST</span>
          <span className="portfolio-regime-card__stat-value">
            {asset.hurst.toFixed(2)}
          </span>
        </div>
      </div>
    </div>
  );
}
