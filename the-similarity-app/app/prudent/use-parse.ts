/**
 * useParsedNarrative — React hook that parses narrative text with a
 * regex-immediate + Claude-upgrade strategy.
 *
 * Why this shape:
 *   - The regex engine in `engine.ts#parseNarrative` is synchronous and
 *     fast enough to run on every keystroke. We run it inline (via
 *     `useMemo`) so the caller always has a non-empty state on the
 *     first render, without ever touching setState from an effect.
 *   - The Claude-backed server route (`/api/prudent/parse`) is slower
 *     (up to ~8s) but produces higher quality events. We fire that in
 *     the background, debounced, and store only the "override" in
 *     state. The final state returned to the caller is derived — if
 *     the override matches the current text, we return it; otherwise
 *     we return the regex result for the current text.
 *   - A change in `text` cancels any in-flight API request via
 *     AbortController to avoid late responses clobbering fresher state.
 *
 * State shape rationale:
 *   - We do NOT mirror `text` into state (that would require a setState
 *     in an effect — an anti-pattern that causes cascading renders).
 *     Instead, the final ParseState is recomputed on every render from
 *     the current `text` + the latest API override. This is effectively
 *     free because React only re-renders on state/prop changes and the
 *     derivation is O(1) once the regex useMemo has cached.
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
 *     update the override state.
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
 * The override stored in state when the API returns a Claude-quality
 * result. The `text` field is the narrative the override was computed
 * for — we compare against the current `text` prop before honoring
 * the override so stale overrides never leak into a newer state.
 */
interface ApiOverride {
  text: string;
  events: Event[];
  series: Point[];
}

export function useParsedNarrative(
  text: string,
  options?: UseParsedNarrativeOptions,
): ParseState {
  const debounceMs = options?.debounceMs ?? DEFAULT_DEBOUNCE_MS;

  // Immediate regex pass, memoized on text. This is what the caller
  // sees on the very first render — guaranteed non-empty as long as
  // the text has parseable content. React caches this between renders
  // so re-renders don't re-run the regex unless `text` changed.
  const regexResult = useMemo(() => parseNarrative(text), [text]);

  // The API override — null until the server returns a Claude result
  // for the current text. We reconcile against `text` on every render
  // so a stale override (from a prior `text`) is invisible to the
  // caller.
  const [override, setOverride] = useState<ApiOverride | null>(null);

  // Loading / error flags for the background fetch. These are
  // independent of the override content so flipping them doesn't
  // churn the events/series references.
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Ref to the current AbortController so a new text change can cancel
  // the previous in-flight fetch. Stored in a ref rather than state
  // because mutating it shouldn't trigger re-renders.
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    // Don't fire the API for empty input — the regex produces the
    // correct empty-series output and there's nothing for Claude to
    // analyze.
    if (!text.trim()) {
      // If the previous text wasn't empty, make sure any in-flight
      // fetch is aborted so it doesn't post a stale override into
      // state.
      abortRef.current?.abort();
      return;
    }

    // Schedule the API call after the debounce window. Using
    // setTimeout rather than any external debounce lib so the hook
    // has zero new dependencies.
    const timer = setTimeout(() => {
      // Cancel any previous in-flight request. AbortError in the fetch
      // .catch() below is handled silently — we only act on responses
      // from non-aborted requests.
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setLoading(true);
      setError(null);

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
          // Only install an override when the API genuinely upgraded
          // to Claude. A `regex` response from the API is equivalent
          // to what we already show, so we just clear `loading`.
          if (data.source === "claude") {
            setOverride({ text, events: data.events, series: data.series });
          }
          setLoading(false);
        })
        .catch((err: unknown) => {
          // AbortError from a superseded request is expected — just
          // stop. Other errors are kept in state so the UI can
          // surface them if desired.
          if (controller.signal.aborted) return;
          const message = err instanceof Error ? err.message : String(err);
          setError(message);
          setLoading(false);
        });
    }, debounceMs);

    return () => {
      clearTimeout(timer);
      // Cancel any in-flight request when `text` changes again before
      // the debounce fires or the fetch resolves.
      abortRef.current?.abort();
    };
  }, [text, debounceMs]);

  // Derive the final state from the current `text`, the regex result,
  // and the API override. This is pure — no setState here, no cascading
  // renders. If the override matches the current text, it wins;
  // otherwise the regex result is displayed.
  return useMemo<ParseState>(() => {
    if (!text.trim()) {
      return {
        events: regexResult.events,
        series: regexResult.series,
        source: "idle",
        loading,
        error,
      };
    }
    if (override && override.text === text) {
      return {
        events: override.events,
        series: override.series,
        source: "api",
        loading,
        error,
      };
    }
    return {
      events: regexResult.events,
      series: regexResult.series,
      source: "regex",
      loading,
      error,
    };
  }, [text, regexResult, override, loading, error]);
}
