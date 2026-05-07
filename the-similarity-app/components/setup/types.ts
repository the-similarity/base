export type SetupBar = {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
};

export type SetupTemplate = {
  id: string;
  userId: string;
  name: string;
  symbol: string;
  timeframe: string;
  source: "chart_region" | "live_capture";
  bars: SetupBar[];
  createdAt: string;
};

export type AnalogContinuation = {
  forwardBars: SetupBar[];
  returnPct: number;
  maxDrawdownPct: number;
};

export type SetupAnalog = {
  id: string;
  setupId: string;
  rank: number;
  symbol: string;
  timeframe: string;
  startAt: string;
  endAt: string;
  score: number;
  confidence: number;
  templateBars: SetupBar[];
  analogBars: SetupBar[];
  continuation: AnalogContinuation;
};

export type ScannerAlert = {
  id: string;
  setupId: string;
  symbol: string;
  timeframe: string;
  firedAt: string;
  score: number;
  confidence: number;
  currentBars: SetupBar[];
  analog: SetupAnalog;
};

export type FeedbackTargetType = "analog" | "alert";

export type FeedbackPayload = {
  targetType: FeedbackTargetType;
  targetId: string;
  value: "up" | "down";
  note?: string;
};

export type DisclaimerConsent = {
  userId: string;
  consentText: string;
  acceptedAt: string;
};

