/**
 * useParsedNarrative — React hook that parses narrative text with a
 * regex-immediate + Claude-upgrade strategy.
 *
 * Why this shape:
 *   - The regex engine in `engine.ts#parseNarrative` is synchronous and
 *     fast enough to run on every keystroke. We run it inline so the
 *     caller always has a non-empty state on the first render.
 *   - The Claude-backed server route (`/api/prudent/parse`) is slower
 *     (up to ~8s) but produces higher quality events. We fire that in
 *     the background, debounced, and swap the state when a 'claude'
 *     response arrives. If the API returns 'regex' (because the server
 *     has no ANTHROPIC_API_KEY or the model errored), we keep the
 *     already-present regex state unchanged.
 *   - A change in `text` cancels any in-flight API request via
 *     AbortController to avoid late responses clobbering fresher state.
 *
 * Integration (future follow-up PR — Team B):
 *   dashboard.tsx currently does:
 *     const { events, series } = useMemo(() => parseNarrative(text), [text]);
 *   The one-line swap is:
 *     const { events, series } = useParsedNarrative(text);
 *   This hook is designed to be a drop-in so the swap is truly a
 *   one-liner. Do NOT perform that swap in this PR — dashboard.tsx is
 *   owned by Team B who may be editing it in parallel.
 *
 * Invariants:
 *   - Returns synchronously on first render with a populated state
 *     (regex pass) unless `text` is the empty string.
 *   - `loading` is true only while a fetch is in flight; regex work is
 *     effectively instantaneous.
 *   - `source === 'idle'` only on the empty-text initial state, before
 *     any parsing has happened.
 *   - AbortController attached to every fetch; aborted requests don't
 *     update state.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { parseNarrative, type Event, type Point } from "./engine";

export interface ParseState {
  /** Parsed events — populated from regex initially, upgraded to Claude if available. */
  events: Event[];
  /** 193-step valence series computed from events + baseline. */
  series: Point[];
  /** Which pipeline produced the current state. `idle` = no parse has run yet. */
  source: "api" | "regex" | "idle";
  /** True while a background API call is in flight. */
  loading: boolean;
  /** Non-null when the last API call failed in a non-fallback way. */
  error: string | null;
}

interface ApiResponse {
  events: Event[];
  series: Point[];
  source: "claude" | "regex";
}

interface UseParsedNarrativeOptions {
  /** Milliseconds to wait after text changes before calling the API. Default 350. */
  debounceMs?: number;
}

const DEFAULT_DEBOUNCE_MS = 350;
const API_URL = "/api/prudent/parse";

/**
 * Synchronously compute the regex result for a given text. Memoized via
 * useMemo in the hook body so re-renders don't re-run the regex unless
 * `text` changed.
 */
function regexParse(text: string): { events: Event[]; series: Point[] } {
  return parseNarrative(text);
}

export function useParsedNarrative(
  text: string,
  options?: UseParsedNarrativeOptions,
): ParseState {
  const debounceMs = options?.debounceMs ?? DEFAULT_DEBOUNCE_MS;

  // Immediate regex pass, memoized on text. This is what the caller
  // sees on the very first render — guaranteed non-empty as long as
  // the text has parseable content.
  const regexResult = useMemo(() => regexParse(text), [text]);

  // Initial state. When text is empty we mark source='idle' so the
  // caller can distinguish "no parse yet" from "regex produced empty".
  const [state, setState] = useState<ParseState>(() => ({
    events: regexResult.events,
    series: regexResult.series,
    source: text.trim() ? "regex" : "idle",
    loading: false,
    error: null,
  }));

  // Keep the displayed regex result in sync with `text` even before
  // the debounced API call fires. Without this, typing would show the
  // FIRST parse forever until the API answered.
  useEffect(() => {
    // If we already have an 'api' result for this exact text, don't
    // clobber it with regex — the API wins and we should keep showing
    // its output. This branch is rare in practice because `text`
    // changing invalidates any prior API result in the next effect.
    setState((prev) => {
      if (prev.source === "api" && prev.events === regexResult.events) {
        return prev;
      }
      return {
        events: regexResult.events,
        series: regexResult.series,
        source: text.trim() ? "regex" : "idle",
        loading: prev.loading,
        error: null,
      };
    });
  }, [regexResult, text]);

  // Ref to the current AbortController so a new text change can cancel
  // the previous in-flight fetch. Stored in a ref rather than state
  // because mutating it shouldn't trigger re-renders.
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    // Don't fire the API for empty input — the regex produces the
    // correct empty-series output and there's nothing for Claude to
    // analyze.
    if (!text.trim()) return;

    // Schedule the API call after the debounce window. Using
    // setTimeout rather than any external debounce lib so the hook
    // has zero new dependencies.
    const timer = setTimeout(() => {
      // Cancel any previous in-flight request. AbortError in the fetch
      // .catch() below is handled silently — we only replace state
      // with responses from non-aborted requests.
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setState((prev) => ({ ...prev, loading: true, error: null }));

      fetch(API_URL, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ text }),
        signal: controller.signal,
      })
        .then(async (res) => {
          if (!res.ok) {
            throw new Error(`HTTP ${res.status}`);
          }
          return (await res.json()) as ApiResponse;
        })
        .then((data) => {
          // If this fetch was superseded by a newer one, drop the
          // result silently. The newer request will own the final
          // state update.
          if (controller.signal.aborted) return;
          // Only replace state when the API genuinely upgraded to
          // Claude. A `regex` response from the API is equivalent to
          // what we already show, so we just clear `loading`.
          if (data.source === "claude") {
            setState({
              events: data.events,
              series: data.series,
              source: "api",
              loading: false,
              error: null,
            });
          } else {
            setState((prev) => ({ ...prev, loading: false, error: null }));
          }
        })
        .catch((err: unknown) => {
          // AbortError from a superseded request is expected — just
          // stop. Other errors are kept in state so the UI can
          // surface them if desired.
          if (controller.signal.aborted) return;
          const message = err instanceof Error ? err.message : String(err);
          setState((prev) => ({ ...prev, loading: false, error: message }));
        });
    }, debounceMs);

    return () => {
      clearTimeout(timer);
      // Cancel any in-flight request when `text` changes again before
      // the debounce fires or the fetch resolves.
      abortRef.current?.abort();
    };
  }, [text, debounceMs]);

  return state;
}
