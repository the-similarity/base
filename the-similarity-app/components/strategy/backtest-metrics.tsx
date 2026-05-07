"use client";

export interface BacktestData {
  winRate: number;
  avgReturn: number;
  sharpeRatio: number;
  totalSignals: number;
  longCount: number;
  shortCount: number;
}

interface BacktestMetricsProps {
  data: BacktestData | null;
}

function valueColor(val: number): string {
  if (val > 0) return "positive";
  if (val < 0) return "negative";
  return "neutral";
}

function WinRateRing({ rate }: { rate: number }) {
  const r = 24;
  const circumference = 2 * Math.PI * r;
  const offset = circumference * (1 - rate / 100);
  const color = rate >= 50 ? "var(--positive)" : "var(--negative)";

  return (
    <div className="strategy-winrate-ring">
      <svg width="56" height="56" viewBox="0 0 56 56">
        <circle
          className="strategy-winrate-ring-bg"
          cx="28"
          cy="28"
          r={r}
        />
        <circle
          className="strategy-winrate-ring-fill"
          cx="28"
          cy="28"
          r={r}
          stroke={color}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
        />
      </svg>
      <div className="strategy-winrate-label">{rate}%</div>
    </div>
  );
}

export function BacktestMetrics({ data }: BacktestMetricsProps) {
  if (!data) return null;

  return (
    <div>
      <div className="strategy-section-label">Backtest Results</div>
      <div className="strategy-metrics">
        <div className="strategy-metric-card">
          <WinRateRing rate={data.winRate} />
          <div className="strategy-metric-label">Win Rate</div>
        </div>

        <div className="strategy-metric-card">
          <div className={`strategy-metric-value ${valueColor(data.avgReturn)}`}>
            {data.avgReturn > 0 ? "+" : ""}
            {data.avgReturn.toFixed(2)}%
          </div>
          <div className="strategy-metric-label">Avg Return</div>
        </div>

        <div className="strategy-metric-card">
          <div className={`strategy-metric-value ${valueColor(data.sharpeRatio)}`}>
            {data.sharpeRatio.toFixed(2)}
          </div>
          <div className="strategy-metric-label">Sharpe Ratio</div>
        </div>

        <div className="strategy-metric-card">
          <div className="strategy-metric-value neutral">{data.totalSignals}</div>
          <div className="strategy-metric-label">Total Matches</div>
        </div>

        <div className="strategy-metric-card">
          <div className="strategy-metric-value positive">{data.longCount}</div>
          <div className="strategy-metric-label">Long</div>
          <div className="strategy-metric-sub">
            {((data.longCount / data.totalSignals) * 100).toFixed(0)}% of total
          </div>
        </div>

        <div className="strategy-metric-card">
          <div className="strategy-metric-value negative">{data.shortCount}</div>
          <div className="strategy-metric-label">Short</div>
          <div className="strategy-metric-sub">
            {((data.shortCount / data.totalSignals) * 100).toFixed(0)}% of total
          </div>
        </div>
      </div>
    </div>
  );
}
