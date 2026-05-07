"use client";

import type {
  DisclaimerConsent,
  FeedbackPayload,
  SetupAnalog,
  SetupBar,
  SetupTemplate,
} from "./types";

const CONSENT_KEY = "ts-setup-scanner:disclaimer-consent";
const SETUPS_KEY = "ts-setup-scanner:setups";
const FEEDBACK_KEY = "ts-setup-scanner:feedback";
const DISCLAIMER_TEXT =
  "Not financial advice. Past performance does not guarantee future results.";

function readJson<T>(key: string, fallback: T): T {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function writeJson<T>(key: string, value: T): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // The API client is a stub until backend worktree A lands. Losing
    // client-side persistence is acceptable; crashing signup is not.
  }
}

export function getDisclaimerText(): string {
  return DISCLAIMER_TEXT;
}

export async function saveDisclaimerConsent(
  userId: string,
): Promise<DisclaimerConsent> {
  const consent: DisclaimerConsent = {
    userId,
    consentText: DISCLAIMER_TEXT,
    acceptedAt: new Date().toISOString(),
  };
  writeJson(CONSENT_KEY, consent);
  return consent;
}

export function hasDisclaimerConsent(): boolean {
  return readJson<DisclaimerConsent | null>(CONSENT_KEY, null) !== null;
}

export async function saveSetupTemplate(
  template: SetupTemplate,
): Promise<SetupTemplate> {
  const setups = readJson<SetupTemplate[]>(SETUPS_KEY, []);
  const next = [template, ...setups.filter(s => s.id !== template.id)].slice(0, 20);
  writeJson(SETUPS_KEY, next);
  return template;
}

export async function submitFeedback(
  feedback: FeedbackPayload,
): Promise<FeedbackPayload> {
  const existing = readJson<Array<FeedbackPayload & { createdAt: string }>>(
    FEEDBACK_KEY,
    [],
  );
  writeJson(FEEDBACK_KEY, [
    { ...feedback, createdAt: new Date().toISOString() },
    ...existing,
  ]);
  return feedback;
}

function scaleBars(seed: SetupBar[], multiplier: number, offsetBars: number): SetupBar[] {
  const baseTime = Date.now() - offsetBars * 86_400_000;
  return seed.map((bar, i) => {
    const close = bar.close * multiplier;
    const open = bar.open * multiplier;
    const high = Math.max(open, close, bar.high * multiplier);
    const low = Math.min(open, close, bar.low * multiplier);
    return {
      timestamp: new Date(baseTime + i * 86_400_000).toISOString(),
      open,
      high,
      low,
      close,
      volume: bar.volume,
    };
  });
}

function buildContinuation(anchor: SetupBar[], rank: number): SetupBar[] {
  const last = anchor[anchor.length - 1]?.close ?? 100;
  return Array.from({ length: 24 }, (_, i) => {
    const drift = (rank % 2 === 0 ? 1 : -1) * (0.0018 * (i + 1));
    const pulse = Math.sin((i + rank) / 4) * 0.006;
    const close = last * (1 + drift + pulse);
    const open = i === 0 ? last : last * (1 + drift * 0.8 + pulse * 0.7);
    return {
      timestamp: new Date(Date.now() + i * 86_400_000).toISOString(),
      open,
      high: Math.max(open, close) * 1.004,
      low: Math.min(open, close) * 0.996,
      close,
    };
  });
}

export async function runColdBacktest(
  setup: SetupTemplate,
): Promise<SetupAnalog[]> {
  const symbols = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XAUUSD", "EURUSD",
    "GBPUSD", "USDJPY", "AUDUSD", "BNBUSDT", "LINKUSDT",
  ];
  await new Promise(resolve => setTimeout(resolve, 350));
  return Array.from({ length: 20 }, (_, i) => {
    const rank = i + 1;
    const multiplier = 0.82 + rank * 0.021;
    const analogBars = scaleBars(setup.bars, multiplier, 220 + rank * 17);
    const forwardBars = buildContinuation(analogBars, rank);
    const start = analogBars[0]?.timestamp ?? setup.createdAt;
    const end = analogBars[analogBars.length - 1]?.timestamp ?? setup.createdAt;
    const first = forwardBars[0]?.close ?? 1;
    const last = forwardBars[forwardBars.length - 1]?.close ?? first;
    return {
      id: `analog-${setup.id}-${rank}`,
      setupId: setup.id,
      rank,
      symbol: symbols[i % symbols.length],
      timeframe: setup.timeframe,
      startAt: start,
      endAt: end,
      score: Math.max(0.42, 0.94 - i * 0.018),
      confidence: Math.max(0.38, 0.88 - i * 0.02),
      templateBars: setup.bars,
      analogBars,
      continuation: {
        forwardBars,
        returnPct: ((last - first) / first) * 100,
        maxDrawdownPct: -1 * (1.2 + (rank % 6) * 0.7),
      },
    };
  });
}

export function buildSetupTemplate(params: {
  name: string;
  userId?: string;
  symbol: string;
  timeframe: string;
  source: SetupTemplate["source"];
  bars: SetupBar[];
}): SetupTemplate {
  return {
    id: `setup-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
    userId: params.userId ?? "alpha-user",
    name: params.name,
    symbol: params.symbol,
    timeframe: params.timeframe,
    source: params.source,
    bars: params.bars,
    createdAt: new Date().toISOString(),
  };
}

