/**
 * URL state serialization for the workstation.
 *
 * A share-link round-trip contract between the address bar and the Retrieve
 * workstation. The contract is deliberately compact (2-3 char keys) so
 * pasted links in a Slack thread or a PR description stay readable and
 * short — and small enough that the 2k-ish URL limits in some corporate
 * proxies never bite.
 *
 * -------------------------------------------------------------------------
 *  Key schema (stable — changing these silently invalidates existing links)
 * -------------------------------------------------------------------------
 *   ds   dataset id           "stocks/spy/1d"
 *   qs   query window start   integer bar index  (>= 0)
 *   ql   query window length  integer bar count  (>= 2, <= 2000)
 *   k    top-K                integer            (>= 1, <= 50)
 *   h    horizon              integer bars       (>= 1, <= 2000)
 *   cm   chart mode           "fast" | "pro"
 *   va   view range start     integer bar index  (>= 0)
 *   vb   view range end       integer bar index  (>= 0)
 *   p    pinned analog ids    comma-separated, max 50 ids
 *   sa   show analogs mode    "top3" | "all" | "pinned"
 *   th   theme                "light" | "dark"
 *   sr   surface              free-form short slug (retrieve, represent, …)
 *
 * -------------------------------------------------------------------------
 *  Invariants
 * -------------------------------------------------------------------------
 *  1. Serialization is TOTAL over the state shape but PARTIAL in the
 *     output: default-valued fields are OMITTED so URLs stay short in the
 *     common case. The caller must supply the defaults explicitly — this
 *     module has no dependency on WorkstationSettings.
 *  2. Parsing is DEFENSIVE: malformed values (NaN, negatives, invalid enums,
 *     overflow) are silently dropped rather than raised. The caller always
 *     receives a best-effort partial state that is safe to spread over
 *     defaults. This keeps a bad link from crashing the page — the worst
 *     outcome is "the link didn't restore some fields".
 *  3. Round-trip stability: for any WorkstationUrlState `s` with in-range
 *     values, `parseUrlState(serializeUrlState(s))` equals `s`. This is
 *     tested explicitly in tests/url-state.test.ts.
 *  4. Pinned lists are clamped to MAX_PINNED (50) ids. A shared link that
 *     embedded hundreds of pins would defeat the "curated subset" UX and
 *     balloon URL length — 50 is plenty for any realistic hand-curation.
 *  5. Empty strings are treated as "absent" on parse. An `?p=` with no
 *     value yields undefined, not an empty array. This matches the common
 *     URL convention and avoids the ambiguity of "was this cleared or
 *     never set?".
 */

// Upper bound on pinned analog ids persisted into a share-link.
// Rationale: the right panel surfaces at most top-K analogs (currently
// capped at 50 in the Top-K selector), and the UI workflow for curating
// more than that is degenerate. A hard cap here prevents a corrupted
// localStorage set leaking into the URL.
const MAX_PINNED = 50;

// Integer clamps for numeric fields. Chosen to be permissive enough to
// accommodate daily/hourly/minute timeframes with years of history, while
// rejecting obvious garbage (negatives, 2^32 overflows).
const MAX_BAR_INDEX = 1_000_000; // ~2740 years of daily bars
const MAX_K = 50;
const MAX_HORIZON = 2000;
const MAX_QUERY_LEN = 2000;

// Whitelisted enum values for fields that must round-trip a specific set.
const CHART_MODES = ["fast", "pro"] as const;
const SHOW_ANALOGS = ["top3", "all", "pinned"] as const;
const THEMES = ["light", "dark"] as const;

/**
 * Shape of the deserialized URL state.
 *
 * Every field is optional: a share-link that only pins a dataset + horizon
 * omits the rest, and the caller fills in defaults from its own settings.
 * Consumers should spread this over their defaults, not vice versa.
 */
export interface WorkstationUrlState {
  dataset?: string;
  queryStart?: number;
  queryLen?: number;
  k?: number;
  horizon?: number;
  chartMode?: "fast" | "pro";
  viewStart?: number;
  viewEnd?: number;
  pinned?: string[];
  showAnalogs?: "top3" | "all" | "pinned";
  theme?: "light" | "dark";
  surface?: string;
}

/**
 * Parse a non-negative integer within [0, max].
 *
 * Returns undefined for anything that fails to be a finite, in-range
 * integer — including empty strings, decimals, NaN, Infinity, and
 * negative values. The caller treats undefined as "field absent" and
 * falls back to its default.
 *
 * We don't accept floats even when they'd round cleanly (`120.0`) because
 * the workstation's bar-index math is strictly integer and round-trip
 * equality would otherwise silently drift across serialize/parse cycles.
 */
function parseNonNegInt(raw: string | null, max: number): number | undefined {
  if (raw === null || raw === "") return undefined;
  // Reject anything that isn't pure digits (no signs, no decimals).
  // Number() would happily parse "+5", "5.0", "5e2" — all of which we
  // want to exclude to keep round-trip equality strict.
  if (!/^\d+$/.test(raw)) return undefined;
  const n = Number(raw);
  if (!Number.isFinite(n)) return undefined;
  if (n < 0 || n > max) return undefined;
  return n;
}

/**
 * Parse a positive integer within [min, max] (inclusive).
 *
 * Convenience wrapper for fields where zero is invalid (queryLen, k,
 * horizon). Otherwise identical to parseNonNegInt.
 */
function parsePosInt(
  raw: string | null,
  min: number,
  max: number,
): number | undefined {
  const v = parseNonNegInt(raw, max);
  if (v === undefined) return undefined;
  if (v < min) return undefined;
  return v;
}

/**
 * Parse the comma-separated pinned-id list.
 *
 * Splits on commas, trims whitespace, drops empty segments, truncates to
 * MAX_PINNED. Preserves the order the ids appear in — the workstation
 * doesn't care about order, but deterministic ordering keeps the
 * round-trip stable.
 *
 * Returns undefined (not `[]`) when the raw value is null/empty so callers
 * can distinguish "URL omitted pins" from "URL explicitly cleared pins".
 * In practice the workstation treats both as empty-set, but the
 * distinction lets the parse layer stay faithful to the wire format.
 */
function parsePinnedList(raw: string | null): string[] | undefined {
  if (raw === null || raw === "") return undefined;
  // Split and clean in one pass. We deliberately do NOT decodeURIComponent
  // again here — URLSearchParams has already done that for us when it
  // yielded the value.
  const ids = raw
    .split(",")
    .map(s => s.trim())
    .filter(s => s.length > 0);
  if (ids.length === 0) return undefined;
  return ids.slice(0, MAX_PINNED);
}

/**
 * Parse a URL query string into a WorkstationUrlState.
 *
 * Accepts the full leading "?" (e.g. `"?ds=stocks.spy.1d&k=6"`) or just
 * the pairs (`"ds=stocks.spy.1d&k=6"`). Unknown keys are silently ignored
 * — forward-compat for future fields. Malformed values are dropped, not
 * raised — the caller always gets a partial state that is safe to merge
 * over defaults.
 *
 * This function is deterministic and pure: no side effects, no reads from
 * `window` or `location`. That's what makes it testable in isolation.
 */
export function parseUrlState(search: string): WorkstationUrlState {
  const out: WorkstationUrlState = {};
  // URLSearchParams handles both "?foo=bar" and "foo=bar" — it strips the
  // leading "?" if present. It also decodes percent-encoding for us.
  const params = new URLSearchParams(
    search.startsWith("?") ? search.slice(1) : search,
  );

  const ds = params.get("ds");
  if (ds && ds.length > 0 && ds.length <= 200) {
    // Length cap guards against a pathological 10kb dataset id in a
    // malicious link. 200 chars is comfortably more than any real
    // "assetClass/symbol/timeframe" id in the catalog.
    out.dataset = ds;
  }

  const qs = parseNonNegInt(params.get("qs"), MAX_BAR_INDEX);
  if (qs !== undefined) out.queryStart = qs;

  const ql = parsePosInt(params.get("ql"), 2, MAX_QUERY_LEN);
  if (ql !== undefined) out.queryLen = ql;

  const k = parsePosInt(params.get("k"), 1, MAX_K);
  if (k !== undefined) out.k = k;

  const h = parsePosInt(params.get("h"), 1, MAX_HORIZON);
  if (h !== undefined) out.horizon = h;

  const cm = params.get("cm");
  if (cm && (CHART_MODES as readonly string[]).includes(cm)) {
    out.chartMode = cm as WorkstationUrlState["chartMode"];
  }

  const va = parseNonNegInt(params.get("va"), MAX_BAR_INDEX);
  if (va !== undefined) out.viewStart = va;

  const vb = parseNonNegInt(params.get("vb"), MAX_BAR_INDEX);
  if (vb !== undefined) out.viewEnd = vb;

  // Cross-field sanity: if both view bounds are present but inverted,
  // drop them both rather than quietly flipping. The workstation's
  // ViewRange component could theoretically handle either order, but
  // we want the URL contract to stay "what you see is what you get".
  if (
    out.viewStart !== undefined &&
    out.viewEnd !== undefined &&
    out.viewEnd <= out.viewStart
  ) {
    delete out.viewStart;
    delete out.viewEnd;
  }

  const pinned = parsePinnedList(params.get("p"));
  if (pinned !== undefined) out.pinned = pinned;

  const sa = params.get("sa");
  if (sa && (SHOW_ANALOGS as readonly string[]).includes(sa)) {
    out.showAnalogs = sa as WorkstationUrlState["showAnalogs"];
  }

  const th = params.get("th");
  if (th && (THEMES as readonly string[]).includes(th)) {
    out.theme = th as WorkstationUrlState["theme"];
  }

  const sr = params.get("sr");
  if (sr && sr.length > 0 && sr.length <= 50) {
    // Surface slugs are free-form so a future surface (e.g. `g n` render)
    // doesn't require a code change here, but we cap the length so a
    // link can't embed a huge blob in this field.
    out.surface = sr;
  }

  return out;
}

/**
 * Serialize a WorkstationUrlState to a URL query string (no leading "?").
 *
 * Emits only keys whose value is DEFINED on the input. That's how
 * "default-valued fields are omitted" is implemented: the caller decides
 * which keys to include by either setting them or leaving them undefined.
 * A typical call site computes `serializeUrlState({ dataset: ..., pinned: ... })`
 * only when a field differs from its default — the helper itself has no
 * opinion on what "default" means.
 *
 * Ordering: the emitted keys follow the schema-declared order above so
 * that shared links are byte-identical when the same state is serialized
 * from different call sites. This also makes URL diffs easy to read in
 * review comments.
 *
 * Pinned lists longer than MAX_PINNED are truncated — same cap as parse,
 * so a round-trip from a legit state is always stable.
 */
export function serializeUrlState(state: WorkstationUrlState): string {
  const params = new URLSearchParams();

  if (state.dataset !== undefined && state.dataset !== "") {
    params.set("ds", state.dataset);
  }
  if (state.queryStart !== undefined) {
    params.set("qs", String(state.queryStart));
  }
  if (state.queryLen !== undefined) {
    params.set("ql", String(state.queryLen));
  }
  if (state.k !== undefined) {
    params.set("k", String(state.k));
  }
  if (state.horizon !== undefined) {
    params.set("h", String(state.horizon));
  }
  if (state.chartMode !== undefined) {
    params.set("cm", state.chartMode);
  }
  if (state.viewStart !== undefined) {
    params.set("va", String(state.viewStart));
  }
  if (state.viewEnd !== undefined) {
    params.set("vb", String(state.viewEnd));
  }
  if (state.pinned !== undefined && state.pinned.length > 0) {
    // Clamp on write so a caller that stuffed 100 ids into the state
    // still round-trips cleanly with the parse side.
    const clamped = state.pinned.slice(0, MAX_PINNED);
    params.set("p", clamped.join(","));
  }
  if (state.showAnalogs !== undefined) {
    params.set("sa", state.showAnalogs);
  }
  if (state.theme !== undefined) {
    params.set("th", state.theme);
  }
  if (state.surface !== undefined && state.surface !== "") {
    params.set("sr", state.surface);
  }

  return params.toString();
}

/**
 * Public re-export of the pin cap so the workstation can surface it in
 * future UX (e.g. "you have 52 pins, only the first 50 will be shared").
 */
export const URL_STATE_MAX_PINNED = MAX_PINNED;
