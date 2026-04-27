"use client";

import { useState, useCallback } from "react";
import Link from "next/link";
import { StrategyCard } from "../../components/strategy/strategy-card";
import { ParamSlider } from "../../components/strategy/param-slider";
import { SignalTable, type Signal } from "../../components/strategy/signal-table";
import {
  BacktestMetrics,
  type BacktestData,
} from "../../components/strategy/backtest-metrics";

/* ── Strategy Templates ── */

interface StrategyTemplate {
  id: string;
  icon: string;
  name: string;
  description: string;
  params: string[];
  defaults: {
    minConfidence: number;
    forecastThreshold: number;
    maxSignals: number;
  };
  weights: Record<string, number>;
}

const METHODS = [
  "Shape",
  "Dynamics",
  "Prefilter",
  "Profile",
  "Scaling",
  "Engine",
  "Rhythm",
  "Decomposition",
  "Topology",
] as const;

const templates: StrategyTemplate[] = [
  {
    id: "momentum",
    icon: "\u2197",
    name: "Momentum",
    description: "Ride strong trends using pattern continuation signals",
    params: ["High confidence", "Trend-following", "Wide stops"],
    defaults: { minConfidence: 72, forecastThreshold: 0.035, maxSignals: 5 },
    weights: {
      Shape: 0.9, Dynamics: 0.7, Prefilter: 0.5, Profile: 0.8,
      Scaling: 0.6, Engine: 0.9, Rhythm: 0.4, Decomposition: 0.5, Topology: 0.3,
    },
  },
  {
    id: "mean-reversion",
    icon: "\u21C4",
    name: "Mean Reversion",
    description: "Fade extremes when patterns suggest price snapback",
    params: ["Tight stops", "Counter-trend", "High frequency"],
    defaults: { minConfidence: 65, forecastThreshold: 0.020, maxSignals: 8 },
    weights: {
      Shape: 0.6, Dynamics: 0.9, Prefilter: 0.7, Profile: 0.5,
      Scaling: 0.8, Engine: 0.4, Rhythm: 0.9, Decomposition: 0.8, Topology: 0.7,
    },
  },
  {
    id: "breakout",
    icon: "\u26A1",
    name: "Breakout",
    description: "Detect range compression and capture explosive moves",
    params: ["Low frequency", "Large targets", "Regime-aware"],
    defaults: { minConfidence: 80, forecastThreshold: 0.050, maxSignals: 3 },
    weights: {
      Shape: 0.7, Dynamics: 0.5, Prefilter: 0.9, Profile: 0.9,
      Scaling: 0.7, Engine: 0.8, Rhythm: 0.6, Decomposition: 0.4, Topology: 0.9,
    },
  },
];

/* ── Mock Signal Generators ── */

function generateMockSignals(
  templateId: string,
  minConf: number,
  maxSignals: number,
): Signal[] {
  const base: { [key: string]: Signal[] } = {
    momentum: [
      { type: "LONG", confidence: 89, entry: 4521.30, stopLoss: 4485.10, takeProfit: 4612.50, reason: "Strong uptrend continuation — Shape match 0.94 with Nov 2023 rally", window: "60d" },
      { type: "LONG", confidence: 82, entry: 4498.75, stopLoss: 4462.00, takeProfit: 4576.20, reason: "Engine eigenvalue > 0.98, forward evolution bullish", window: "45d" },
      { type: "SHORT", confidence: 76, entry: 4550.00, stopLoss: 4582.30, takeProfit: 4478.60, reason: "Momentum exhaustion detected — Rhythm decomposition divergence", window: "30d" },
      { type: "LONG", confidence: 74, entry: 4510.20, stopLoss: 4478.90, takeProfit: 4589.40, reason: "Profile motif match — pre-breakout pattern from Q2 2024", window: "90d" },
      { type: "LONG", confidence: 71, entry: 4535.60, stopLoss: 4506.10, takeProfit: 4604.80, reason: "Prefilter frequency spike — bullish regime transition", window: "60d" },
      { type: "SHORT", confidence: 68, entry: 4568.40, stopLoss: 4598.20, takeProfit: 4502.70, reason: "Topology persistence diagram anomaly at resistance", window: "45d" },
    ],
    "mean-reversion": [
      { type: "SHORT", confidence: 84, entry: 4580.20, stopLoss: 4602.10, takeProfit: 4538.90, reason: "2.3 std deviation above 20d mean — Dynamics snapback pattern", window: "15d" },
      { type: "LONG", confidence: 81, entry: 4412.50, stopLoss: 4392.80, takeProfit: 4458.30, reason: "Decomposition intrinsic mode suggests oversold bottom", window: "20d" },
      { type: "SHORT", confidence: 78, entry: 4572.60, stopLoss: 4591.40, takeProfit: 4541.20, reason: "Rhythm leader exponent declining — mean reversion imminent", window: "10d" },
      { type: "LONG", confidence: 75, entry: 4435.80, stopLoss: 4418.50, takeProfit: 4472.10, reason: "Scaling distance metric at extremum", window: "25d" },
      { type: "SHORT", confidence: 72, entry: 4561.30, stopLoss: 4578.90, takeProfit: 4532.70, reason: "Carry reversal from VIX to SPX", window: "15d" },
      { type: "LONG", confidence: 69, entry: 4445.20, stopLoss: 4428.60, takeProfit: 4479.80, reason: "Dynamics correlation flip — historical mean convergence", window: "20d" },
      { type: "SHORT", confidence: 66, entry: 4555.40, stopLoss: 4572.00, takeProfit: 4528.60, reason: "Prefilter symbolic distance at 95th percentile", window: "10d" },
      { type: "LONG", confidence: 63, entry: 4450.90, stopLoss: 4435.20, takeProfit: 4482.10, reason: "Topology distance contraction", window: "30d" },
    ],
    breakout: [
      { type: "LONG", confidence: 92, entry: 4560.00, stopLoss: 4518.50, takeProfit: 4685.20, reason: "Range compression (Bollinger BW 0.02) + Prefilter rare-word breakout", window: "120d" },
      { type: "LONG", confidence: 86, entry: 4545.30, stopLoss: 4498.70, takeProfit: 4648.90, reason: "Profile discord — regime shift detected", window: "90d" },
      { type: "SHORT", confidence: 83, entry: 4590.50, stopLoss: 4638.20, takeProfit: 4492.30, reason: "Topology birth-death pair at critical level — breakdown pattern", window: "60d" },
    ],
  };

  const signals = (base[templateId] ?? base["momentum"]).filter(
    (s: Signal) => s.confidence >= minConf,
  );
  return signals.slice(0, maxSignals);
}

function generateBacktest(templateId: string): BacktestData {
  const data: Record<string, BacktestData> = {
    momentum: {
      winRate: 61,
      avgReturn: 1.83,
      sharpeRatio: 1.42,
      totalSignals: 147,
      longCount: 108,
      shortCount: 39,
    },
    "mean-reversion": {
      winRate: 58,
      avgReturn: 0.92,
      sharpeRatio: 1.18,
      totalSignals: 312,
      longCount: 162,
      shortCount: 150,
    },
    breakout: {
      winRate: 44,
      avgReturn: 3.21,
      sharpeRatio: 1.67,
      totalSignals: 63,
      longCount: 41,
      shortCount: 22,
    },
  };
  return data[templateId] ?? data["momentum"];
}

/* ── Page Component ── */

export default function StrategyPage() {
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null);
  const [minConfidence, setMinConfidence] = useState(72);
  const [forecastThreshold, setForecastThreshold] = useState(0.035);
  const [maxSignals, setMaxSignals] = useState(5);
  const [weights, setWeights] = useState<Record<string, number>>(() => {
    const w: Record<string, number> = {};
    for (const m of METHODS) w[m] = 0.5;
    return w;
  });
  const [signals, setSignals] = useState<Signal[]>([]);
  const [backtest, setBacktest] = useState<BacktestData | null>(null);

  const selectTemplate = useCallback(
    (id: string) => {
      const tpl = templates.find((t) => t.id === id);
      if (!tpl) return;
      setSelectedTemplate(id);
      setMinConfidence(tpl.defaults.minConfidence);
      setForecastThreshold(tpl.defaults.forecastThreshold);
      setMaxSignals(tpl.defaults.maxSignals);
      setWeights({ ...tpl.weights });
      setSignals([]);
      setBacktest(null);
    },
    [],
  );

  const handleApply = useCallback(() => {
    if (!selectedTemplate) return;
    setSignals(generateMockSignals(selectedTemplate, minConfidence, maxSignals));
    setBacktest(generateBacktest(selectedTemplate));
  }, [selectedTemplate, minConfidence, maxSignals]);

  const updateWeight = useCallback((method: string, value: number) => {
    setWeights((prev) => ({ ...prev, [method]: value }));
  }, []);

  return (
    <div className="strategy-page">
      {/* ── Top Bar ── */}
      <div className="strategy-topbar">
        <Link href="/workstation" className="strategy-topbar-logo">
          THE SIMILARITY
        </Link>
        <div className="terminal-topbar-sep" />
        <span className="strategy-topbar-title">Strategy Builder</span>
      </div>

      {/* ── Content ── */}
      <div className="strategy-content">
        {/* ── Strategy Selector ── */}
        <div>
          <div className="strategy-section-label">Select Strategy Template</div>
          <div className="strategy-templates">
            {templates.map((tpl) => (
              <StrategyCard
                key={tpl.id}
                icon={tpl.icon}
                name={tpl.name}
                description={tpl.description}
                params={tpl.params}
                selected={selectedTemplate === tpl.id}
                onClick={() => selectTemplate(tpl.id)}
              />
            ))}
          </div>
        </div>

        {/* ── Config + Signals ── */}
        {selectedTemplate && (
          <div className="strategy-body">
            {/* ── Configuration Panel ── */}
            <div className="strategy-config">
              <div className="strategy-config-section">
                <div className="strategy-config-section-title">Parameters</div>
                <ParamSlider
                  label="Min Confidence"
                  value={minConfidence}
                  min={0}
                  max={100}
                  step={1}
                  onChange={setMinConfidence}
                  format={(v) => `${v}%`}
                />
                <ParamSlider
                  label="Forecast Threshold"
                  value={forecastThreshold}
                  min={0}
                  max={0.1}
                  step={0.001}
                  onChange={setForecastThreshold}
                  format={(v) => v.toFixed(3)}
                />
                <ParamSlider
                  label="Max Signals"
                  value={maxSignals}
                  min={1}
                  max={10}
                  step={1}
                  onChange={setMaxSignals}
                />
              </div>

              <div className="strategy-config-section">
                <div className="strategy-config-section-title">
                  Method Weights
                </div>
                <div className="strategy-weights">
                  {METHODS.map((method) => (
                    <div key={method} className="strategy-weight-item">
                      <div className="strategy-weight-header">
                        <span className="strategy-weight-name">{method}</span>
                        <span className="strategy-weight-val">
                          {(weights[method] ?? 0.5).toFixed(1)}
                        </span>
                      </div>
                      <input
                        type="range"
                        className="strategy-weight-slider"
                        min={0}
                        max={1}
                        step={0.1}
                        value={weights[method] ?? 0.5}
                        onChange={(e) =>
                          updateWeight(method, parseFloat(e.target.value))
                        }
                      />
                    </div>
                  ))}
                </div>
              </div>

              <button className="strategy-apply-btn" onClick={handleApply}>
                Apply &amp; Generate Signals
              </button>
            </div>

            {/* ── Signal Preview ── */}
            <SignalTable signals={signals} />
          </div>
        )}

        {/* ── Backtest Metrics ── */}
        <BacktestMetrics data={backtest} />
      </div>
    </div>
  );
}
