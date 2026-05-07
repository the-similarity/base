"use client";

export interface Signal {
  type: "LONG" | "SHORT" | "FLAT";
  confidence: number;
  entry: number;
  stopLoss: number;
  takeProfit: number;
  reason: string;
  window: string;
}

interface SignalTableProps {
  signals: Signal[];
}

function badgeClass(type: Signal["type"]): string {
  switch (type) {
    case "LONG":
      return "strategy-badge strategy-badge-long";
    case "SHORT":
      return "strategy-badge strategy-badge-short";
    default:
      return "strategy-badge strategy-badge-flat";
  }
}

export function SignalTable({ signals }: SignalTableProps) {
  if (signals.length === 0) {
    return (
      <div className="strategy-signals">
        <div className="strategy-empty">
          <div className="strategy-empty-icon">&#x25C9;</div>
          <div className="strategy-empty-text">
            Select a strategy and apply configuration to run a backtest
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="strategy-signals">
      <div className="strategy-signals-header">
        <span className="strategy-signals-title">Match Preview</span>
        <span className="strategy-signals-count">
          {signals.length} match{signals.length !== 1 ? "es" : ""}
        </span>
      </div>

      <div className="strategy-signal-row strategy-signal-head">
        <span>Type</span>
        <span>Confidence</span>
        <span>Entry</span>
        <span>Stop</span>
        <span>Target</span>
        <span>Reason</span>
        <span>Window</span>
      </div>

      <div className="strategy-signal-list">
        {signals.map((signal, i) => (
          <div key={i} className="strategy-signal-row">
            <span>
              <span className={badgeClass(signal.type)}>{signal.type}</span>
            </span>
            <div className="strategy-confidence">
              <div className="strategy-confidence-bar">
                <div
                  className="strategy-confidence-fill"
                  style={{ width: `${signal.confidence}%` }}
                />
              </div>
              <span className="strategy-confidence-value">
                {signal.confidence}
              </span>
            </div>
            <span className="strategy-price">{signal.entry.toFixed(2)}</span>
            <span className="strategy-price strategy-price-stop">
              {signal.stopLoss.toFixed(2)}
            </span>
            <span className="strategy-price strategy-price-target">
              {signal.takeProfit.toFixed(2)}
            </span>
            <span className="strategy-reason" title={signal.reason}>
              {signal.reason}
            </span>
            <span className="strategy-window">{signal.window}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
