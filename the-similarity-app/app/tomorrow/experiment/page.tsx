"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  parseNarrative,
  runExperimentReport,
  type ExperimentReport,
} from "../engine";
import { buildHistoryFromEntries } from "../storage";
import { seedDemoEntries } from "../_components/demo-seed";
import { useEngine } from "../_components/engine-context";

const STARTER_PROMPTS = [
  "Woke up anxious about the deadline. Morning was rough, but I took a walk at noon. A friend texted me and the afternoon started to lift. I want to know what happens today.",
  "Tired morning, bad sleep, lots of meetings. I skipped breakfast and feel scattered. Planning to go to the gym later if I can get unstuck.",
  "Good start. Coffee, clean apartment, focused first block. Lunch with a friend later and a quiet evening planned.",
];

type DictationStatus = "idle" | "listening" | "unsupported" | "blocked";

type SpeechRecognitionResultLike = {
  isFinal: boolean;
  0: { transcript: string };
};

type SpeechRecognitionEventLike = {
  resultIndex: number;
  results: {
    length: number;
    [index: number]: SpeechRecognitionResultLike;
  };
};

type SpeechRecognitionErrorLike = {
  error?: string;
};

type SpeechRecognitionLike = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorLike) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  }
}

export default function TomorrowExperimentPage() {
  const { entries, openComposer, reloadEntries } = useEngine();
  const [text, setText] = useState(STARTER_PROMPTS[0]);
  const [dictationStatus, setDictationStatus] = useState<DictationStatus>("idle");
  const [dictationMessage, setDictationMessage] = useState("Free browser dictation for now. Desktop voice can run locally later.");
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const dictationBaseRef = useRef("");
  const parsed = useMemo(() => parseNarrative(text), [text]);
  const avg = useMemo(
    () => Math.round(parsed.series.reduce((a, b) => a + b.v, 0) / parsed.series.length),
    [parsed.series],
  );
  const history = useMemo(() => buildHistoryFromEntries(entries, avg), [entries, avg]);
  const report = useMemo(
    () => runExperimentReport(history, parsed.series, parsed.events),
    [history, parsed.events, parsed.series],
  );
  const externalRisk = useMemo(() => assessExternalRisk(text), [text]);

  const loadDemo = () => {
    seedDemoEntries();
    reloadEntries();
  };

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!getSpeechRecognitionConstructor()) {
      setDictationStatus("unsupported");
      setDictationMessage("Dictation is not available in this browser. Chrome and Edge usually support it.");
    }
    return () => {
      recognitionRef.current?.abort();
      recognitionRef.current = null;
    };
  }, []);

  const toggleDictation = () => {
    if (dictationStatus === "listening") {
      recognitionRef.current?.stop();
      setDictationStatus("idle");
      setDictationMessage("Dictation stopped. Edit the text before reading the day.");
      return;
    }

    const Recognition = getSpeechRecognitionConstructor();
    if (!Recognition) {
      setDictationStatus("unsupported");
      setDictationMessage("Dictation is not available in this browser. Chrome and Edge usually support it.");
      return;
    }

    const recognition = new Recognition();
    dictationBaseRef.current = text;
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-US";
    recognition.onresult = (event) => {
      let transcript = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        transcript += event.results[i][0].transcript;
      }
      setText(mergeDictationText(dictationBaseRef.current, transcript));
    };
    recognition.onerror = (event) => {
      const blocked = event.error === "not-allowed" || event.error === "service-not-allowed";
      setDictationStatus(blocked ? "blocked" : "idle");
      setDictationMessage(
        blocked
          ? "Microphone access is blocked. Allow the mic in the browser to dictate."
          : "Dictation stopped. Try again or type the entry manually.",
      );
    };
    recognition.onend = () => {
      setDictationStatus((current) => (current === "listening" ? "idle" : current));
    };
    recognitionRef.current = recognition;

    try {
      recognition.start();
      setDictationStatus("listening");
      setDictationMessage("Listening through free browser dictation. Speak naturally.");
    } catch {
      setDictationStatus("idle");
      setDictationMessage("Dictation could not start. Try again after the browser finishes the current mic session.");
    }
  };

  return (
    <div className="tomorrow-experiment-page">
      <section className="tomorrow-command-grid">
        <div className="tomorrow-input-panel">
          <div className="tomorrow-section-heading">
            <div>
              <div className="tomorrow-kicker">live read</div>
              <div className="tomorrow-title-line">What will happen today?</div>
            </div>
            <span className="tomorrow-status-dot">ready</span>
          </div>
          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            rows={8}
            className="tomorrow-signal-input"
            aria-label="Current entry for Tomorrow read"
          />
          <div className="tomorrow-dictation-bar">
            <button
              className={dictationStatus === "listening" ? "tomorrow-primary-button" : "tomorrow-quiet-button"}
              type="button"
              onClick={toggleDictation}
              disabled={dictationStatus === "unsupported"}
            >
              {dictationStatus === "listening" ? "stop dictation" : "dictate"}
            </button>
            <div className="tomorrow-dictation-copy">
              <span data-active={dictationStatus === "listening"}>
                {dictationStatus === "listening" ? "mic live" : dictationStatus}
              </span>
              {dictationMessage}
            </div>
          </div>
          <div className="tomorrow-button-row">
            {STARTER_PROMPTS.map((prompt, i) => (
              <button
                key={prompt}
                onClick={() => setText(prompt)}
                className="tomorrow-quiet-button"
              >
                example {i + 1}
              </button>
            ))}
            <button
              onClick={loadDemo}
              className="tomorrow-primary-button"
            >
              load sample days
            </button>
            <button
              onClick={openComposer}
              className="tomorrow-quiet-button"
            >
              log real entry
            </button>
          </div>
        </div>
        <div className="tomorrow-read-stack">
          <ProCard />
          <NaturalLanguageCard report={report} />
        </div>
      </section>

      <div className="tomorrow-grid tomorrow-grid-large">
        <PathExperiment report={report} />
        <RealityBoundary risk={externalRisk} />
      </div>

      <div className="tomorrow-grid">
        <CounterfactualExperiment report={report} />
        <BacktestExperiment report={report} />
      </div>

      <div className="tomorrow-grid">
        <AblationExperiment report={report} />
        <CaseStudyExperiment report={report} />
      </div>

      <style>{`
        .tomorrow-experiment-page {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }

        .tomorrow-command-grid,
        .tomorrow-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 16px;
        }

        .tomorrow-grid-large {
          grid-template-columns: 1.1fr 0.9fr;
        }

        .tomorrow-input-panel,
        .tomorrow-panel {
          background: var(--panel);
          border: 1px solid var(--line);
          border-radius: 8px;
          min-width: 0;
        }

        .tomorrow-input-panel {
          padding: 18px;
          display: flex;
          flex-direction: column;
          gap: 13px;
        }

        .tomorrow-section-heading {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 12px;
        }

        .tomorrow-kicker,
        .tomorrow-status-dot,
        .tomorrow-eyebrow {
          font-family: var(--mono);
          font-size: 10px;
          color: var(--muted);
          text-transform: uppercase;
          letter-spacing: 0;
          font-weight: 650;
        }

        .tomorrow-title-line {
          color: var(--ink);
          font-size: 18px;
          font-weight: 650;
          margin-top: 4px;
        }

        .tomorrow-status-dot {
          border: 1px solid var(--line-mid);
          border-radius: 999px;
          padding: 5px 8px;
          white-space: nowrap;
          color: var(--ink);
          background: var(--app-bg);
        }

        .tomorrow-signal-input {
          width: 100%;
          min-height: 164px;
          resize: vertical;
          border: 1px solid var(--line-mid);
          border-radius: 6px;
          padding: 14px 15px;
          background: var(--app-bg);
          color: var(--ink);
          font-family: var(--serif);
          font-size: 18px;
          line-height: 1.55;
          outline: none;
        }

        .tomorrow-signal-input:focus {
          border-color: var(--ink);
        }

        .tomorrow-button-row {
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
        }

        .tomorrow-dictation-bar {
          display: grid;
          grid-template-columns: auto 1fr;
          gap: 10px;
          align-items: center;
          border: 1px solid var(--line);
          border-radius: 6px;
          padding: 9px;
          background: var(--app-bg);
        }

        .tomorrow-dictation-copy {
          color: var(--muted);
          font-size: 12px;
          line-height: 1.35;
        }

        .tomorrow-dictation-copy span {
          display: inline-flex;
          margin-right: 7px;
          color: var(--ink);
          font-family: var(--mono);
          font-size: 10px;
          text-transform: uppercase;
          font-weight: 650;
        }

        .tomorrow-dictation-copy span[data-active="true"] {
          color: var(--green);
        }

        .tomorrow-quiet-button,
        .tomorrow-primary-button {
          min-height: 31px;
          border-radius: 6px;
          padding: 0 10px;
          font-size: 11px;
          font-weight: 650;
          font-family: var(--mono);
          text-transform: uppercase;
          letter-spacing: 0;
        }

        .tomorrow-quiet-button {
          border: 1px solid var(--line-mid);
          color: var(--muted);
          background: transparent;
        }

        .tomorrow-quiet-button:disabled {
          cursor: not-allowed;
          opacity: 0.5;
        }

        .tomorrow-primary-button {
          border: 1px solid var(--ink);
          background: var(--ink);
          color: var(--app-bg);
        }

        .tomorrow-read-stack {
          display: grid;
          grid-template-rows: auto 1fr;
          gap: 12px;
          min-width: 0;
        }

        .tomorrow-pro-card,
        .tomorrow-console {
          border: 1px solid var(--line);
          border-radius: 8px;
          background: var(--panel);
          color: var(--ink);
        }

        .tomorrow-pro-card {
          padding: 12px 13px;
          display: grid;
          grid-template-columns: 1fr auto;
          gap: 12px;
          align-items: center;
        }

        .tomorrow-pro-price {
          font-size: 24px;
          font-weight: 750;
          line-height: 1;
          white-space: nowrap;
        }

        .tomorrow-price-stack {
          display: flex;
          align-items: center;
          gap: 10px;
          justify-content: flex-end;
        }

        .tomorrow-pro-price span {
          font-size: 11px;
          color: var(--muted);
          font-weight: 600;
          margin-left: 3px;
        }

        .tomorrow-pro-action {
          min-height: 31px;
          border-radius: 6px;
          border: 1px solid var(--accent);
          background: var(--accent);
          color: #fff;
          padding: 0 11px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          font-size: 11px;
          font-weight: 750;
          font-family: var(--mono);
          text-transform: uppercase;
          letter-spacing: 0;
          white-space: nowrap;
          text-decoration: none;
        }

        .tomorrow-console {
          padding: 17px;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          gap: 16px;
          min-height: 242px;
        }

        .tomorrow-console .tomorrow-eyebrow,
        .tomorrow-pro-card .tomorrow-eyebrow {
          color: var(--muted);
        }

        .tomorrow-console-text {
          margin: 10px 0 0;
          color: var(--ink);
          font-family: var(--serif);
          font-size: 24px;
          line-height: 1.28;
          font-style: italic;
        }

        .tomorrow-console-row {
          display: flex;
          gap: 7px;
          flex-wrap: wrap;
        }

        .tomorrow-dark-pill {
          border: 1px solid var(--line);
          border-radius: 999px;
          padding: 5px 9px;
          display: flex;
          gap: 6px;
          align-items: center;
          color: var(--ink);
          font-size: 12px;
          font-weight: 650;
        }

        .tomorrow-dark-pill span:first-child {
          color: var(--muted);
          font-family: var(--mono);
          font-size: 9px;
          text-transform: uppercase;
        }

        .tomorrow-panel {
          padding: 16px 18px 18px;
        }

        .tomorrow-panel-head {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 10px;
          margin-bottom: 14px;
        }

        .tomorrow-panel-title {
          font-size: 14px;
          font-weight: 650;
          color: var(--ink);
        }

        .tomorrow-panel-sub {
          font-size: 11px;
          color: var(--muted);
          margin-top: 3px;
        }

        .tomorrow-path-stack,
        .tomorrow-list-stack {
          display: flex;
          flex-direction: column;
          gap: 9px;
        }

        .tomorrow-path-card,
        .tomorrow-case-card,
        .tomorrow-reality-block {
          border: 1px solid var(--line);
          border-radius: 6px;
          padding: 12px 13px;
          background: var(--app-bg);
        }

        .tomorrow-path-card[data-primary="true"] {
          border-color: var(--ink);
        }

        .tomorrow-path-title,
        .tomorrow-list-title {
          font-size: 13px;
          font-weight: 650;
          color: var(--ink);
        }

        .tomorrow-path-copy,
        .tomorrow-quote {
          font-family: var(--serif);
          font-size: 16px;
          line-height: 1.45;
          color: var(--ink);
          font-style: italic;
          margin-top: 5px;
        }

        .tomorrow-small-copy {
          font-size: 12px;
          color: var(--muted);
          line-height: 1.45;
          margin-top: 7px;
        }

        .tomorrow-reality-grid,
        .tomorrow-case-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 10px;
        }

        .tomorrow-list-row {
          display: grid;
          grid-template-columns: 1fr auto;
          gap: 10px;
          align-items: center;
          border-bottom: 1px solid var(--line);
          padding-bottom: 9px;
        }

        .tomorrow-list-row:last-child {
          border-bottom: 0;
          padding-bottom: 0;
        }

        @media (max-width: 980px) {
          .tomorrow-command-grid,
          .tomorrow-grid {
            grid-template-columns: 1fr !important;
          }
        }

        @media (max-width: 680px) {
          .tomorrow-section-heading,
          .tomorrow-pro-card,
          .tomorrow-price-stack,
          .tomorrow-panel-head,
          .tomorrow-list-row {
            grid-template-columns: 1fr;
            flex-direction: column;
            align-items: stretch;
          }

          .tomorrow-reality-grid,
          .tomorrow-case-grid,
          .tomorrow-dictation-bar {
            grid-template-columns: 1fr;
          }
        }
      `}</style>
    </div>
  );
}

function getSpeechRecognitionConstructor(): SpeechRecognitionConstructor | null {
  if (typeof window === "undefined") return null;
  return window.SpeechRecognition ?? window.webkitSpeechRecognition ?? null;
}

function mergeDictationText(base: string, transcript: string): string {
  const spoken = transcript.trim();
  if (!spoken) return base;
  if (!base.trim()) return spoken;
  return `${base.trimEnd()} ${spoken}`;
}

interface ExternalRisk {
  verdict: string;
  score: number;
  factors: string[];
  missing: string;
  action: string;
}

function assessExternalRisk(text: string): ExternalRisk {
  const lower = text.toLowerCase();
  const checks: Array<{ label: string; re: RegExp; weight: number }> = [
    { label: "driving or commute mentioned", re: /\b(drive|driving|car|traffic|commute|subway|bus|road|crosswalk)\b/, weight: 18 },
    { label: "walking or biking near roads", re: /\b(walk|walking|bike|biking|cycling|run|running)\b/, weight: 10 },
    { label: "tired, low sleep, or drained", re: /\b(tired|exhausted|drained|bad sleep|no sleep|sleepy|sluggish)\b/, weight: 14 },
    { label: "late night or poor visibility", re: /\b(night|late|dark|rain|storm|snow|fog)\b/, weight: 12 },
    { label: "stress or distraction", re: /\b(anxious|stressed|scattered|distracted|rushing|deadline)\b/, weight: 10 },
    { label: "alcohol or impaired context", re: /\b(drink|drinks|drunk|bar|party|weed|high)\b/, weight: 16 },
  ];
  const hits = checks.filter((check) => check.re.test(lower));
  const score = Math.min(100, hits.reduce((sum, hit) => sum + hit.weight, 0));
  const verdict =
    score >= 45
      ? "Tomorrow cannot know if you will get hit by a car. Your entry only mentions travel or attention risks."
      : score >= 20
        ? "Tomorrow cannot predict a car accident. It only sees mild travel or attention risk in what you wrote."
        : "No. Tomorrow cannot know whether a random accident will happen tomorrow.";
  return {
    verdict,
    score,
    factors: hits.map((hit) => hit.label),
    missing: "It does not know your route, weather, traffic, driver behavior, location, or plain chance.",
    action:
      score >= 20
        ? "Treat this as a safety nudge: slow down at crossings, avoid distracted walking/driving, and do not travel tired if you can avoid it."
        : "For rare outside events, use normal safety habits instead of treating this read as proof.",
  };
}

function NaturalLanguageCard({ report }: { report: ExperimentReport }) {
  const cues = [
    { label: "read", value: confidenceLabel(report.prediction.confidence) },
    { label: "history", value: memoryLabel(report.prediction.matches.length) },
    { label: "tone", value: toneLabel(report) },
  ];
  return (
    <section className="tomorrow-console">
      <div>
        <div className="tomorrow-eyebrow">tomorrow read</div>
        <p className="tomorrow-console-text">
          {report.headline}
        </p>
      </div>
      <div className="tomorrow-console-row">
        {cues.map((cue) => (
          <DarkPill key={cue.label} label={cue.label} value={cue.value} />
        ))}
      </div>
    </section>
  );
}

function ProCard() {
  return (
    <aside className="tomorrow-pro-card">
      <div>
        <div className="tomorrow-eyebrow">Tomorrow Pro</div>
        <div style={{ color: "var(--ink)", fontSize: 13, fontWeight: 650, marginTop: 4 }}>
          Daily reads, voice notes, and saved-day reminders.
        </div>
      </div>
      <div className="tomorrow-price-stack">
        <div className="tomorrow-pro-price">
          $29.99<span>/mo</span>
        </div>
        <Link className="tomorrow-pro-action" href="/tomorrow/subscribe">
          Start Pro
        </Link>
      </div>
    </aside>
  );
}

function PathExperiment({ report }: { report: ExperimentReport }) {
  return (
    <Panel title="Today plan" sub="The day in three usable versions">
      <div className="tomorrow-path-stack">
        {report.prediction.paths.map((path) => (
          <div
            key={path.id}
            className="tomorrow-path-card"
            data-primary={path.id === "base"}
          >
            <div className="tomorrow-path-title">
              {pathPlainTitle(path.id)}
            </div>
            <div className="tomorrow-path-copy">
              {pathPlainCopy(path.id)}
            </div>
            <div className="tomorrow-small-copy">
              {path.summary}.
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function BacktestExperiment({ report }: { report: ExperimentReport }) {
  const comparisons = report.backtest.baselines.map((baseline) => ({
    name: baselineName(baseline.name),
    result: baseline.mae >= report.backtest.engineMae ? "better than this guess" : "this guess was steadier",
  }));
  return (
    <Panel title="Should I trust it?" sub="A plain check against basic guesses">
      <p className="tomorrow-quote" style={{ marginTop: 0, marginBottom: 13 }}>
        {trustCopy(report)}
      </p>
      <div className="tomorrow-list-stack">
        {comparisons.map((comparison) => (
          <div key={comparison.name} className="tomorrow-list-row">
            <div style={{ fontSize: 12, color: "var(--muted)" }}>{comparison.name}</div>
            <div style={{ fontSize: 11, color: comparison.result.startsWith("better") ? "var(--green)" : "var(--warm-strong)", fontWeight: 650 }}>
              {comparison.result}
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function RealityBoundary({ risk }: { risk: ExternalRisk }) {
  return (
    <Panel title="What it can't know" sub="A clear limit on the read">
      <div className="tomorrow-list-stack">
        <div className="tomorrow-reality-block">
          <div className="tomorrow-eyebrow">real world</div>
          <div className="tomorrow-quote">
          {risk.verdict}
          </div>
        </div>
        <div className="tomorrow-reality-grid">
          <div className="tomorrow-reality-block">
            <div className="tomorrow-eyebrow">can see</div>
            <div className="tomorrow-small-copy" style={{ color: "var(--ink)" }}>
              Mood changes, repeated days, stress, body state, people, and likely next move.
            </div>
          </div>
          <div className="tomorrow-reality-block">
            <div className="tomorrow-eyebrow">cannot see</div>
            <div className="tomorrow-small-copy" style={{ color: "var(--ink)" }}>
              Random accidents, other people&apos;s choices, live traffic, weather, and chance.
            </div>
          </div>
        </div>
        <div className="tomorrow-small-copy" style={{ marginTop: 0 }}>
          {riskFactorsCopy(risk)}
        </div>
        <div className="tomorrow-small-copy" style={{ marginTop: 0 }}>
          {risk.missing}
        </div>
        <div style={{ fontSize: 12, color: "var(--ink)", lineHeight: 1.45, fontWeight: 650 }}>
          {risk.action}
        </div>
      </div>
    </Panel>
  );
}

function AblationExperiment({ report }: { report: ExperimentReport }) {
  const strongest = report.ablations.reduce((best, row) =>
    Math.abs(row.deltaFromFull) > Math.abs(best.deltaFromFull) ? row : best,
  report.ablations[0]);
  return (
    <Panel title="What changed it" sub="The parts of your entry that moved the read">
      <div className="tomorrow-list-stack">
        {report.ablations.map((row) => (
          <div key={row.name} className="tomorrow-list-row">
            <div>
              <div className="tomorrow-list-title">{plainAblationName(row.name)}</div>
              <div className="tomorrow-small-copy" style={{ marginTop: 2 }}>
                {row === strongest ? "This part carries the read the most." : "This part matters, but it does not run the whole story."}
              </div>
            </div>
            <div style={{ textAlign: "right", color: row.deltaFromFull >= 0 ? "var(--green)" : "var(--warm-strong)", fontSize: 12, fontWeight: 650 }}>
              {deltaWords(row.deltaFromFull)}
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function CounterfactualExperiment({ report }: { report: ExperimentReport }) {
  return (
    <Panel title="What to do next" sub="Small moves that can help today">
      <div className="tomorrow-list-stack">
        {report.counterfactuals.map((row) => (
          <div key={row.move.id} className="tomorrow-list-row">
            <div>
            <div className="tomorrow-list-title">
              {row.move.label}
            </div>
            <div className="tomorrow-small-copy" style={{ marginTop: 4 }}>
              {row.move.reason}. {counterfactualShift(row.expectedNextAvg, report.prediction.expectedNextAvg)}
            </div>
            </div>
            <div className="tomorrow-status-dot">{moveLevel(row.expectedNextAvg, report.prediction.expectedNextAvg)}</div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function CaseStudyExperiment({ report }: { report: ExperimentReport }) {
  const best = report.backtest.cases[0];
  const miss = report.backtest.cases[report.backtest.cases.length - 1];
  return (
    <Panel title="Why this read" sub="Past entries behind it">
      <div className="tomorrow-case-grid">
        <CaseCard label="Best hit" item={best} />
        <CaseCard label="Hardest miss" item={miss} />
      </div>
    </Panel>
  );
}

function CaseCard({
  label,
  item,
}: {
  label: string;
  item: ExperimentReport["backtest"]["cases"][number] | undefined;
}) {
  if (!item) {
    return <div style={{ color: "var(--muted)", fontSize: 13 }}>Load demo history for cases.</div>;
  }
  return (
    <div className="tomorrow-case-card">
      <div className="tomorrow-eyebrow">
        {label}
      </div>
      <div className="tomorrow-quote">
        {caseStudyCopy(item)}
      </div>
      <div className="tomorrow-small-copy">{item.decoded}</div>
    </div>
  );
}

function Panel({ title, sub, children }: { title: string; sub: string; children: React.ReactNode }) {
  return (
    <section className="tomorrow-panel">
      <div className="tomorrow-panel-head">
        <div>
          <div className="tomorrow-panel-title">{title}</div>
          <div className="tomorrow-panel-sub">{sub}</div>
        </div>
      </div>
      {children}
    </section>
  );
}

function DarkPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="tomorrow-dark-pill">
      <span>{label}</span>
      <span>{value}</span>
    </div>
  );
}

function confidenceLabel(confidence: number): string {
  if (confidence >= 0.62) return "strong read";
  if (confidence >= 0.48) return "usable read";
  return "soft read";
}

function memoryLabel(matches: number): string {
  if (matches >= 4) return "enough history";
  if (matches > 0) return "some history";
  return "thin history";
}

function toneLabel(report: ExperimentReport): string {
  const delta = report.prediction.expectedNextAvg - report.prediction.signal.avg;
  if (delta >= 4) return "lifting";
  if (delta <= -4) return "heavier";
  return "steady";
}

function pathPlainTitle(id: string): string {
  if (id === "upside") return "Better version";
  if (id === "downside") return "If it slips";
  return "Most likely";
}

function pathPlainCopy(id: string): string {
  if (id === "upside") return "One helpful move makes the day easier to steer.";
  if (id === "downside") return "If the same stress keeps repeating, the day needs an early reset.";
  return "The day likely keeps following its current mood.";
}

function trustCopy(report: ExperimentReport): string {
  if (report.backtest.cases.length === 0) {
    return "There is not enough saved history yet. Log a few real days so Tomorrow can compare today with your own life.";
  }
  const wins = report.backtest.baselines.filter((baseline) => baseline.mae >= report.backtest.engineMae).length;
  if (wins >= 3) return "Looking at your saved entries, this read beats most basic guesses. Useful, not certain.";
  if (wins >= 1) return "Looking at your saved entries, this read beats some basic guesses. Treat it as a nudge.";
  return "The basic guesses did better here. Treat this read as a question, not an instruction.";
}

function baselineName(name: string): string {
  if (name === "Yesterday repeats") return "Repeating yesterday";
  if (name === "7-day average") return "Your recent average";
  if (name === "Random walk") return "A random wobble";
  if (name === "Sentiment only") return "Mood words only";
  return name;
}

function riskFactorsCopy(risk: ExternalRisk): string {
  if (risk.factors.length === 0) {
    return "Your text does not mention travel, roads, poor sleep, bad visibility, or impaired context.";
  }
  return `Your text mentions ${joinHuman(risk.factors)}. That is not a sign an accident will happen; it is a reminder to move slower around travel.`;
}

function plainAblationName(name: string): string {
  return name
    .replace("No social signal", "Remove people")
    .replace("No body signal", "Remove sleep and body")
    .replace("No tension signal", "Remove stress")
    .replace("No similarity memory", "Ignore saved days")
    .replace("No negative events", "Ignore hard moments");
}

function deltaWords(delta: number): string {
  if (Math.abs(delta) < 2) return "barely moves it";
  if (delta > 0) return "makes it lighter";
  return "makes it heavier";
}

function counterfactualShift(expected: number, current: number): string {
  const lift = expected - current;
  if (lift >= 7) return "This is the strongest move here.";
  if (lift >= 4) return "This should noticeably help today.";
  return "This is a small stabilizer.";
}

function moveLevel(expected: number, current: number): string {
  const lift = expected - current;
  if (lift >= 7) return "primary";
  if (lift >= 4) return "strong";
  return "light";
}

function caseStudyCopy(item: ExperimentReport["backtest"]["cases"][number]): string {
  const predictedHigh = item.predicted >= 50;
  const actualHigh = item.actual >= 50;
  const sameDirection = predictedHigh === actualHigh;
  if (item.error < 8) return "A past entry and the next day lined up closely.";
  if (sameDirection) return "It caught the direction, but the size of the shift was messy.";
  return "This miss came from a day that changed suddenly.";
}

function joinHuman(items: string[]): string {
  if (items.length === 1) return items[0];
  if (items.length === 2) return `${items[0]} and ${items[1]}`;
  return `${items.slice(0, -1).join(", ")}, and ${items[items.length - 1]}`;
}
