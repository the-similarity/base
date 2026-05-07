"use client";

import { useMemo, useState } from "react";
import { FeedbackControl } from "../alerts/feedback-control";
import {
  getDisclaimerText,
  hasDisclaimerConsent,
  runColdBacktest,
  saveDisclaimerConsent,
} from "../setup/setup-scanner-client";
import type { SetupAnalog, SetupTemplate } from "../setup/types";
import styles from "./cold-backtest-onboarding.module.css";

type ColdBacktestOnboardingProps = {
  setup: SetupTemplate;
};

function shortDate(iso: string): string {
  return new Date(iso).toISOString().slice(0, 10);
}

export function ColdBacktestOnboarding({ setup }: ColdBacktestOnboardingProps) {
  const [email, setEmail] = useState("");
  const [accepted, setAccepted] = useState(() => hasDisclaimerConsent());
  const [analogs, setAnalogs] = useState<SetupAnalog[]>([]);
  const [showAll, setShowAll] = useState(false);
  const [loading, setLoading] = useState(false);
  const [slow, setSlow] = useState(false);

  const visibleAnalogs = useMemo(
    () => analogs.slice(0, showAll ? 20 : 5),
    [analogs, showAll],
  );

  async function start(): Promise<void> {
    if (!accepted) return;
    setLoading(true);
    setSlow(false);
    const slowTimer = window.setTimeout(() => setSlow(true), 1000);
    await saveDisclaimerConsent(email || setup.userId);
    const results = await runColdBacktest(setup);
    window.clearTimeout(slowTimer);
    setAnalogs(results);
    setLoading(false);
    setSlow(false);
  }

  return (
    <main className={styles.shell}>
      <div className={styles.inner}>
        <header className={styles.header}>
          <div>
            <span className="label">Setup scanner</span>
            <h1 className={styles.title}>Cold backtest</h1>
            <p className={styles.copy}>
              Define the setup once, then scan the covered crypto, FX, and gold universe for historical analogs.
            </p>
          </div>
          <div className="mono">{setup.symbol} · {setup.timeframe}</div>
        </header>

        <div className={styles.grid}>
          <section className={styles.signup} aria-label="Signup">
            <label className={styles.field}>
              <span className="label">Email</span>
              <input
                className={styles.input}
                type="email"
                value={email}
                placeholder="you@example.com"
                onChange={e => setEmail(e.target.value)}
              />
            </label>
            <label className={styles.consent}>
              <input
                type="checkbox"
                checked={accepted}
                onChange={e => setAccepted(e.target.checked)}
              />
              <span>{getDisclaimerText()}</span>
            </label>
            <button
              type="button"
              className={styles.primary}
              disabled={!accepted || loading}
              onClick={() => void start()}
            >
              {loading ? "Running..." : "Run cold backtest"}
            </button>
            {slow && (
              <div className={styles.progress} aria-label="Backtest loading">
                <i />
              </div>
            )}
          </section>

          <section className={styles.results} aria-label="Ranked analogs">
            {visibleAnalogs.length > 0 && (
              <div className={styles.analogGrid}>
                {visibleAnalogs.map(analog => (
                  <article key={analog.id} className={styles.card}>
                    <div className={styles.cardTop}>
                      <span className={styles.rank}>#{analog.rank}</span>
                      <span className={styles.score}>{analog.score.toFixed(2)}</span>
                    </div>
                    <div>
                      <div className={styles.symbol}>{analog.symbol}</div>
                      <div className={styles.dates}>{shortDate(analog.startAt)} → {shortDate(analog.endAt)}</div>
                    </div>
                    <div className={styles.stats}>
                      Continuation{" "}
                      <span className={analog.continuation.returnPct >= 0 ? styles.positive : styles.negative}>
                        {analog.continuation.returnPct >= 0 ? "+" : ""}
                        {analog.continuation.returnPct.toFixed(1)}%
                      </span>
                      {" "}· confidence {(analog.confidence * 100).toFixed(0)}%
                    </div>
                    <FeedbackControl targetType="analog" targetId={analog.id} compact />
                  </article>
                ))}
              </div>
            )}
            {analogs.length > 5 && !showAll && (
              <button
                type="button"
                className={styles.reveal}
                onClick={() => setShowAll(true)}
              >
                Show 15 more
              </button>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}
