"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { useEngine } from "../_components/engine-context";

const STEPS = [
  {
    title: "Write today",
    copy: "Type or dictate what is going on. Keep it messy; Tomorrow cleans it up.",
  },
  {
    title: "Read the plan",
    copy: "Get a short read on the day and one practical next step.",
  },
  {
    title: "Start Pro",
    copy: "$29.99/mo. Keep the daily read, voice notes, and saved-day reminders.",
  },
];

const INCLUDED = [
  "Daily read in plain language",
  "One next step",
  "Clear limits on what it cannot know",
  "Voice dictation for fast entries",
  "Reminders from similar saved days",
  "Export your entries anytime",
];

export default function SubscribePage() {
  const { entries } = useEngine();
  const [step, setStep] = useState(0);
  const [checkoutNotice, setCheckoutNotice] = useState(false);
  const savedDays = entries.length;
  const priceCopy = useMemo(
    () => savedDays > 0
      ? `${savedDays} saved ${savedDays === 1 ? "day" : "days"} ready for Pro.`
      : "Start with today's read. It gets more useful as you write.",
    [savedDays],
  );

  return (
    <div className="subscribe-page">
      <section className="subscribe-hero">
        <div className="subscribe-copy">
          <div className="subscribe-kicker">Tomorrow Pro</div>
          <h2>A clearer read on your day, every morning.</h2>
          <p>
            Write what is happening. Tomorrow gives you a short read, one next
            step, and reminders from days like this one.
          </p>
          <div className="subscribe-actions">
            <button className="subscribe-primary" type="button" onClick={() => setStep(1)}>
              Start setup
            </button>
            <Link className="subscribe-secondary" href="/tomorrow/experiment">
              Try today&apos;s read
            </Link>
          </div>
        </div>

        <aside className="subscribe-price-card">
          <div className="subscribe-kicker">Pro</div>
          <div className="subscribe-price">$29.99<span>/mo</span></div>
          <p>{priceCopy}</p>
          <button className="subscribe-primary subscribe-full" type="button" onClick={() => setStep(2)}>
            Continue to Pro
          </button>
          <div className="subscribe-fine">Checkout connection is pending for launch.</div>
        </aside>
      </section>

      <section className="subscribe-flow">
        <div className="subscribe-flow-head">
          <div>
            <div className="subscribe-kicker">Setup</div>
            <h3>Three steps, no ceremony.</h3>
          </div>
          <div className="subscribe-step-pill">Step {step + 1} of 3</div>
        </div>

        <div className="subscribe-steps">
          {STEPS.map((item, index) => (
            <button
              key={item.title}
              className="subscribe-step"
              data-active={index === step}
              type="button"
              onClick={() => setStep(index)}
            >
              <span>{index + 1}</span>
              <strong>{item.title}</strong>
              <small>{item.copy}</small>
            </button>
          ))}
        </div>

        <div className="subscribe-checkout-panel">
          <div>
            <div className="subscribe-kicker">Current step</div>
            <h3>{STEPS[step].title}</h3>
            <p>{STEPS[step].copy}</p>
          </div>
          <div className="subscribe-checkout-actions">
            {step < 2 ? (
              <button className="subscribe-primary" type="button" onClick={() => setStep(step + 1)}>
                Next
              </button>
            ) : (
              <button className="subscribe-primary" type="button" onClick={() => setCheckoutNotice(true)}>
                Start $29.99/mo
              </button>
            )}
            <Link className="subscribe-secondary" href="/tomorrow/experiment">
              Preview first
            </Link>
          </div>
          {checkoutNotice ? (
            <div className="subscribe-checkout-note">
              Checkout is not taking payment yet. Wire this final action to Stripe before launch.
            </div>
          ) : null}
        </div>
      </section>

      <section className="subscribe-included">
        <div>
          <div className="subscribe-kicker">Why pay</div>
          <h3>Because a useful read changes the day.</h3>
          <p>
            Free journaling stores what happened. Pro helps you decide what to
            do next while the day is still happening.
          </p>
        </div>
        <div className="subscribe-included-grid">
          {INCLUDED.map((item) => (
            <div key={item}>{item}</div>
          ))}
        </div>
      </section>

      <style>{`
        .subscribe-page {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }

        .subscribe-hero,
        .subscribe-flow,
        .subscribe-included {
          border: 1px solid var(--line);
          border-radius: 8px;
          background: var(--panel);
        }

        .subscribe-hero {
          display: grid;
          grid-template-columns: minmax(0, 1fr) 340px;
          gap: 14px;
          padding: 18px;
        }

        .subscribe-copy h2,
        .subscribe-flow h3,
        .subscribe-included h3,
        .subscribe-checkout-panel h3 {
          margin: 0;
          color: var(--ink);
          line-height: 1.05;
        }

        .subscribe-copy h2 {
          font-size: 40px;
          max-width: 760px;
        }

        .subscribe-copy p,
        .subscribe-price-card p,
        .subscribe-included p,
        .subscribe-checkout-panel p {
          margin: 12px 0 0;
          color: var(--muted);
          font-size: 14px;
          line-height: 1.55;
          max-width: 680px;
        }

        .subscribe-kicker {
          font-family: var(--mono);
          font-size: 10px;
          font-weight: 700;
          text-transform: uppercase;
          color: var(--muted);
          margin-bottom: 8px;
        }

        .subscribe-actions,
        .subscribe-checkout-actions {
          display: flex;
          gap: 9px;
          flex-wrap: wrap;
          margin-top: 18px;
        }

        .subscribe-primary,
        .subscribe-secondary {
          min-height: 38px;
          border-radius: 6px;
          padding: 0 14px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          font-size: 13px;
          font-weight: 700;
          text-decoration: none;
        }

        .subscribe-primary {
          background: var(--accent);
          color: #fff;
          border: 1px solid var(--accent);
        }

        .subscribe-secondary {
          background: var(--panel);
          color: var(--ink);
          border: 1px solid var(--line-mid);
        }

        .subscribe-price-card {
          background: var(--app-bg);
          color: var(--ink);
          border: 1px solid var(--line);
          border-radius: 8px;
          padding: 16px;
          align-self: stretch;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          gap: 14px;
        }

        .subscribe-price-card .subscribe-kicker,
        .subscribe-price-card p,
        .subscribe-fine {
          color: var(--muted);
        }

        .subscribe-price {
          color: var(--ink);
          font-size: 44px;
          font-weight: 800;
          line-height: 1;
        }

        .subscribe-price span {
          font-size: 14px;
          color: var(--muted);
          margin-left: 4px;
        }

        .subscribe-full {
          width: 100%;
        }

        .subscribe-fine {
          font-size: 11px;
          line-height: 1.4;
        }

        .subscribe-flow,
        .subscribe-included {
          padding: 18px;
        }

        .subscribe-flow-head {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 14px;
          margin-bottom: 14px;
        }

        .subscribe-step-pill {
          border: 1px solid var(--line-mid);
          border-radius: 999px;
          padding: 5px 9px;
          font-family: var(--mono);
          font-size: 10px;
          font-weight: 700;
          color: var(--ink);
          white-space: nowrap;
        }

        .subscribe-steps {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 10px;
        }

        .subscribe-step {
          border: 1px solid var(--line);
          border-radius: 8px;
          padding: 13px;
          text-align: left;
          background: var(--app-bg);
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        .subscribe-step[data-active="true"] {
          border-color: var(--ink);
        }

        .subscribe-step span {
          width: 24px;
          height: 24px;
          border-radius: 50%;
          background: var(--accent-soft);
          color: var(--accent-ink);
          display: inline-flex;
          align-items: center;
          justify-content: center;
          font-family: var(--mono);
          font-size: 11px;
          font-weight: 800;
        }

        .subscribe-step strong {
          color: var(--ink);
          font-size: 14px;
        }

        .subscribe-step small {
          color: var(--muted);
          font-size: 12px;
          line-height: 1.45;
        }

        .subscribe-checkout-panel {
          margin-top: 12px;
          border: 1px solid var(--line);
          border-radius: 8px;
          background: var(--app-bg);
          padding: 15px;
          display: grid;
          grid-template-columns: 1fr auto;
          gap: 14px;
          align-items: center;
        }

        .subscribe-checkout-note {
          grid-column: 1 / -1;
          color: var(--muted);
          font-size: 12px;
          line-height: 1.4;
          border-top: 1px solid var(--line);
          padding-top: 12px;
        }

        .subscribe-included {
          display: grid;
          grid-template-columns: 0.85fr 1.15fr;
          gap: 18px;
        }

        .subscribe-included-grid {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 9px;
        }

        .subscribe-included-grid div {
          border: 1px solid var(--line);
          border-radius: 6px;
          padding: 11px 12px;
          color: var(--ink);
          background: var(--app-bg);
          font-size: 13px;
          font-weight: 650;
        }

        @media (max-width: 980px) {
          .subscribe-hero,
          .subscribe-included,
          .subscribe-checkout-panel {
            grid-template-columns: 1fr;
          }
        }

        @media (max-width: 760px) {
          .subscribe-copy h2 {
            font-size: 34px;
          }

          .subscribe-steps,
          .subscribe-included-grid {
            grid-template-columns: 1fr;
          }
        }
      `}</style>
    </div>
  );
}
