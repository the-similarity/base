"use client";

import React from "react";
import Link from "next/link";
import { RegimeCard, type AssetRegime } from "../../components/portfolio/regime-card";
import { DivergenceTable, type DivergencePair } from "../../components/portfolio/divergence-table";
import { FlowNetwork, type FlowEdge } from "../../components/portfolio/flow-network";

/* ── Mock Data ── */

const assets: AssetRegime[] = [
  { name: "Gold Futures", ticker: "GC", regime: "trending_up", volatility: 0.142, slope: 0.018, hurst: 0.63 },
  { name: "Bitcoin", ticker: "BTC", regime: "high_vol", volatility: 0.487, slope: 0.032, hurst: 0.55 },
  { name: "Ethereum", ticker: "ETH", regime: "trending_down", volatility: 0.523, slope: -0.024, hurst: 0.48 },
  { name: "S&P 500", ticker: "SPY", regime: "mean_reverting", volatility: 0.168, slope: 0.003, hurst: 0.41 },
  { name: "Euro/USD", ticker: "EURUSD", regime: "low_vol", volatility: 0.062, slope: -0.001, hurst: 0.44 },
  { name: "Crude Oil", ticker: "CL", regime: "high_vol", volatility: 0.312, slope: -0.015, hurst: 0.52 },
  { name: "10Y Treasury", ticker: "TY", regime: "mean_reverting", volatility: 0.089, slope: 0.002, hurst: 0.38 },
  { name: "Nasdaq 100", ticker: "NQ", regime: "trending_up", volatility: 0.213, slope: 0.021, hurst: 0.58 },
];

const divergences: DivergencePair[] = [
  { assetA: "BTC", assetB: "ETH", historicalCorr: 0.87, recentCorr: 0.52, divergenceScore: 0.35, direction: "decorrelating" },
  { assetA: "SPY", assetB: "NQ", historicalCorr: 0.94, recentCorr: 0.78, divergenceScore: 0.16, direction: "decorrelating" },
  { assetA: "GC", assetB: "TY", historicalCorr: 0.31, recentCorr: 0.58, divergenceScore: 0.27, direction: "recorrelating" },
  { assetA: "CL", assetB: "SPY", historicalCorr: 0.42, recentCorr: 0.11, divergenceScore: 0.31, direction: "decorrelating" },
  { assetA: "EURUSD", assetB: "GC", historicalCorr: 0.48, recentCorr: 0.62, divergenceScore: 0.14, direction: "recorrelating" },
  { assetA: "BTC", assetB: "SPY", historicalCorr: 0.35, recentCorr: 0.08, divergenceScore: 0.27, direction: "decorrelating" },
  { assetA: "CL", assetB: "EURUSD", historicalCorr: 0.29, recentCorr: 0.44, divergenceScore: 0.15, direction: "recorrelating" },
  { assetA: "ETH", assetB: "NQ", historicalCorr: 0.62, recentCorr: 0.38, divergenceScore: 0.24, direction: "decorrelating" },
];

const flows: FlowEdge[] = [
  { source: "SPY", target: "NQ", teForward: 0.142, teReverse: 0.089, netFlow: 0.053, direction: "forward" },
  { source: "BTC", target: "ETH", teForward: 0.231, teReverse: 0.067, netFlow: 0.164, direction: "forward" },
  { source: "GC", target: "EURUSD", teForward: 0.078, teReverse: 0.112, netFlow: -0.034, direction: "reverse" },
  { source: "CL", target: "SPY", teForward: 0.095, teReverse: 0.041, netFlow: 0.054, direction: "forward" },
  { source: "TY", target: "GC", teForward: 0.063, teReverse: 0.088, netFlow: -0.025, direction: "reverse" },
  { source: "BTC", target: "CL", teForward: 0.047, teReverse: 0.031, netFlow: 0.016, direction: "forward" },
  { source: "SPY", target: "EURUSD", teForward: 0.052, teReverse: 0.068, netFlow: -0.016, direction: "reverse" },
];

/* ── Page ── */

export default function PortfolioPage() {
  return (
    <div className="portfolio-page">
      {/* Header */}
      <header className="portfolio-header">
        <div className="portfolio-header__breadcrumb">
          <Link href="/workstation" className="portfolio-header__breadcrumb-link">Terminal</Link>
          <span className="portfolio-header__breadcrumb-sep">/</span>
          <span className="portfolio-header__breadcrumb-current">Portfolio Scanner</span>
        </div>
        <h1 className="portfolio-header__title">Portfolio Scanner</h1>
        <p className="portfolio-header__subtitle">
          Cross-asset regime detection, correlation divergence, and information flow analysis
        </p>
      </header>

      {/* Asset Regime Grid */}
      <section className="portfolio-section">
        <div className="portfolio-section__header">
          <h2 className="portfolio-section__title">Asset Regimes</h2>
          <span className="portfolio-section__count">{assets.length} assets</span>
        </div>
        <div className="portfolio-regime-grid">
          {assets.map((a) => (
            <RegimeCard key={a.ticker} asset={a} />
          ))}
        </div>
      </section>

      {/* Divergence Table */}
      <section className="portfolio-section">
        <div className="portfolio-section__header">
          <h2 className="portfolio-section__title">Correlation Divergence</h2>
          <span className="portfolio-section__count">{divergences.length} pairs</span>
        </div>
        <DivergenceTable data={divergences} />
      </section>

      {/* Flow Network */}
      <section className="portfolio-section">
        <div className="portfolio-section__header">
          <h2 className="portfolio-section__title">Information Flow Network</h2>
          <span className="portfolio-section__count">Transfer Entropy</span>
        </div>
        <FlowNetwork data={flows} />
      </section>
    </div>
  );
}
