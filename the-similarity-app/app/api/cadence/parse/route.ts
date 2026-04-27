/**
 * POST /api/cadence/parse
 *
 * Claude-backed narrative parser for the Cadence pillar, with a graceful
 * regex fallback. Accepts `{text: string}` and returns
 * `{events: Event[], series: Point[], source: 'claude' | 'regex'}`.
 *
 * Pipeline:
 *   1. Validate the request body (zod).
 *   2. If ANTHROPIC_API_KEY is set, attempt a Claude Sonnet 4.6 call via
 *      the raw REST API (`fetch` to https://api.anthropic.com/v1/messages,
 *      no SDK). The system prompt carries `cache_control: ephemeral` so the
 *      lexicon/tag taxonomy is served from the prompt cache on repeat
 *      requests (~90% cheaper after the first hit). We use a structured
 *      tool schema (`extract_valence_events`) so the model can ONLY return
 *      the exact JSON shape we accept — no free-form parsing of the reply.
 *      Time-series integration is done SERVER-SIDE using the same
 *      algorithm as `engine.ts#parseNarrative` so we don't waste output
 *      tokens on the 193-step series.
 *   3. If the key is missing, the call fails for any reason, or the model
 *      returns malformed data that violates the zod schema, we fall back
 *      to the regex engine via `parseNarrative()` imported from
 *      `../../../cadence/engine`. The route is fail-open: a caller always
 *      gets a usable payload.
 *
 * Invariants:
 *   - Response latency is bounded: the Claude fetch is wrapped in an
 *     AbortController with an 8s wall-clock cap. Regex is synchronous
 *     and near-instant, so a worst-case request is ~8s + regex time.
 *   - `events[].delta` ∈ [-30, 30]; `events[].time` ∈ [0, 960]; `tag`
 *     is in a fixed enum; `cert` ∈ [0, 1]. Out-of-bounds values from
 *     the model are clamped rather than rejected so we don't fall back
 *     more often than necessary.
 *   - Deterministic on identical input when Claude is not available: the
 *     regex branch produces byte-identical output for the same text.
 *   - No external npm dependency is added; we use the Next.js built-in
 *     `fetch` + the project's existing `zod`.
 *
 * Why not the Anthropic SDK? The task asks for raw fetch to keep the
 * dependency surface small (this app doesn't use the SDK anywhere else
 * and the only endpoint we need is /v1/messages). The extra typing
 * overhead of the SDK isn't worth it for one call.
 */

import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { parseNarrative, type Event, type Point } from "../../../cadence/engine";

// Fixed tag enum used to constrain the model output. Mirrors the tags
// produced by `engine.ts`'s LEXICON so the downstream UI code doesn't
// need to special-case Claude vs regex output.
const VALID_TAGS = [
  "low",
  "tension",
  "energy",
  "flat",
  "work",
  "move",
  "food",
  "body",
  "quiet",
  "rest",
  "social",
  "rise",
  "high",
] as const;

// Clamps derived from the tool schema. Kept in one place so the clamp
// logic below stays synchronized with the values advertised to the
// model.
const DELTA_MIN = -30;
const DELTA_MAX = 30;
const TIME_MIN = 0;
const TIME_MAX = 960; // 16h * 60min = 960 minutes = full waking window
const CERT_MIN = 0;
const CERT_MAX = 1;

// Series shape: sampled every 5 minutes across 16 hours, inclusive of
// both endpoints (i = 0..192). Matches the exact grid used by
// engine.ts so downstream code can treat Claude output and regex output
// interchangeably.
const SERIES_STEPS = (16 * 60) / 5 + 1; // 193

// Request schema. We use Zod rather than raw typeof checks so a
// malformed payload is rejected with a precise 400 rather than crashing
// mid-handler.
const RequestSchema = z.object({
  text: z.string(),
});

// Schema for the model's tool-use output. The model emits events +
// baseline; we compute the series server-side. This saves hundreds of
// output tokens per call (193 floats) and keeps integration logic in
// one place.
const ModelEventSchema = z.object({
  text: z.string(),
  delta: z.number(),
  tag: z.string(),
  cert: z.number(),
  time: z.number(),
});
const ModelOutputSchema = z.object({
  baseline: z.number().optional(),
  events: z.array(ModelEventSchema),
});

type ModelEvent = z.infer<typeof ModelEventSchema>;

// 8 second wall-clock cap on the Claude call. The user should never
// wait longer than this — if Claude is slow or unreachable, we drop to
// regex and return within ~regex time.
const CLAUDE_TIMEOUT_MS = 8_000;

// Model + API version pinned. Sonnet 4.6 is explicitly requested in
// the task brief; it's the right cost/capability point for a per-
// request parse. anthropic-version header is required by the REST API.
const CLAUDE_MODEL = "claude-sonnet-4-6";
const ANTHROPIC_VERSION = "2023-06-01";
const ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages";

/**
 * Static system prompt. Cached via `cache_control: ephemeral` so repeat
 * requests read from the prompt cache (~0.1x the write cost). Kept
 * deterministic — no timestamps, no request IDs — so the prefix is
 * byte-stable across requests.
 *
 * The prompt describes the parser's job, the tag taxonomy, and the
 * integration model so the extractor returns events compatible with
 * the regex engine's output shape.
 */
const SYSTEM_PROMPT = `You are the Cadence valence parser. You read a free-text narrative of a user's day and extract discrete emotional/activity events as structured data.

# Output contract

You MUST call the tool \`extract_valence_events\` exactly once with a JSON payload of the form:

  {
    "baseline": <number in [0, 100]>,
    "events": [
      { "text": <sentence>, "delta": <number in [-30, 30]>,
        "tag": <one of the valid tags>, "cert": <number in [0, 1]>,
        "time": <integer minutes in [0, 960]> },
      ...
    ]
  }

- \`baseline\` is the user's starting valence before any events (default 50).
- Each event captures ONE salient sentence or phrase.
- \`delta\` is signed change to valence; negative = worse, positive = better.
- \`time\` is minutes after wake (wake = 7am), so 0..960 = 7am..11pm.
- \`cert\` is how confident you are in the delta's sign and magnitude.

# Valid tags (pick the closest match)

- low      — sad, depressed, terrible, devastated, lonely
- tension  — anxious, angry, frustrated, stressed, on edge
- energy   — tired, exhausted, drained, sluggish, groggy
- flat     — bored, okay, meh, dull, uneventful
- work     — meetings, emails, standups, reviews, office tasks
- move     — commute, travel, driving, subway, traffic
- food     — meals, coffee, eating, cooking
- body     — exercise, walking, gym, running, yoga
- quiet    — reading, music, podcasts, introspection
- rest     — naps, sleeping, resting
- social   — friends, calls, hugs, texts, laughing
- rise     — improving, recovering, feeling better, calm, peaceful
- high     — great, flow, breakthrough, thrilled, joy, love

# Magnitude guidance

Calibrate \`delta\`:
- ±3  tiny shift (small observation, background)
- ±8  notable shift (a lunch, a call, mild lift)
- ±14 strong shift (an argument, a rough meeting, a real breakthrough)
- ±25 exceptional event (devastation, euphoria)

Hard cap at ±30. Do not exceed. If the narrative mentions an event but
doesn't describe its valence, assign \`delta: 0\` and \`tag: "flat"\`.

# Time guidance

If the sentence mentions a time-of-day anchor, use it:
- "morning", "woke up"   → 120
- "dawn", "sunrise"      → 0
- "noon", "lunch", "midday" → 300
- "afternoon"            → 420
- "evening", "dinner"    → 660
- "night", "bedtime"     → 840
- "late night"           → 960

If no anchor is present, distribute events roughly evenly through the
narrative, starting near 60 (8am) and advancing 45-75 minutes per
sentence.

# Style

Keep event \`text\` short (≤120 chars), ideally the original sentence
verbatim or the most salient clause. Do NOT editorialize.

Return ONLY the tool call. Do not emit commentary or additional text.`;

/**
 * Tool schema. This is the ONLY allowed shape of the model's output.
 * The Anthropic API enforces the JSON schema on the tool_use block, so
 * a model that disobeys shape will fail validation at the API level,
 * not ours.
 *
 * Claude Sonnet 4.6 supports strict tool-use; we turn on
 * `additionalProperties: false` and list every field in `required` so
 * the model can't smuggle in extra data.
 */
const TOOL_SCHEMA = {
  name: "extract_valence_events",
  description:
    "Emit the structured list of valence events extracted from the user's day narrative.",
  input_schema: {
    type: "object",
    additionalProperties: false,
    properties: {
      baseline: {
        type: "number",
        minimum: 0,
        maximum: 100,
        description: "Starting valence before events are applied.",
      },
      events: {
        type: "array",
        description: "Ordered list of events parsed from the narrative.",
        items: {
          type: "object",
          additionalProperties: false,
          properties: {
            text: { type: "string", description: "The sentence fragment." },
            delta: {
              type: "number",
              minimum: DELTA_MIN,
              maximum: DELTA_MAX,
              description: "Signed change to valence in [-30, 30].",
            },
            tag: {
              type: "string",
              enum: [...VALID_TAGS],
              description: "Category tag for the event.",
            },
            cert: {
              type: "number",
              minimum: CERT_MIN,
              maximum: CERT_MAX,
              description: "Confidence in the delta, 0..1.",
            },
            time: {
              type: "number",
              minimum: TIME_MIN,
              maximum: TIME_MAX,
              description: "Minutes after 7am wake, 0..960.",
            },
          },
          required: ["text", "delta", "tag", "cert", "time"],
        },
      },
    },
    required: ["events"],
  },
} as const;

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

/**
 * Integrate a baseline + event list into the 193-step valence series.
 *
 * This mirrors the integration loop in `engine.ts#parseNarrative`: we
 * march through 5-minute steps, apply any events whose `time` has been
 * reached, and ease the current value toward the running target with
 * the same smoothing constants + gentle sinusoidal jitter. The goal is
 * visual parity with the regex path, so a UI swap from one source to
 * another doesn't change the chart's character.
 */
function integrateSeries(events: Event[], baseline: number): Point[] {
  const series: Point[] = new Array(SERIES_STEPS);
  let y = clamp(baseline, 0, 100);
  let target = y;
  const applied = new Set<number>();
  for (let i = 0; i < SERIES_STEPS; i++) {
    const minute = i * 5;
    // Apply any events whose time has been reached this step. Using
    // a Set to dedupe prevents double-apply if an event's `time`
    // rounds onto the exact boundary.
    for (const ev of events) {
      if (applied.has(ev.id)) continue;
      if (ev.time <= minute) {
        target = clamp(target + ev.delta, 0, 100);
        applied.add(ev.id);
        ev.appliedAt = minute;
      }
    }
    // Exponential ease toward target; same 0.25 coefficient as the
    // regex engine so the curve shape is visually identical.
    y += (target - y) * 0.25;
    // Deterministic "texture" — two out-of-phase sinusoids — so the
    // series isn't a flat-lined piecewise-linear staircase.
    y += (Math.sin(minute / 23) + Math.cos(minute / 17)) * 0.4;
    series[i] = { t: minute, v: clamp(y, 0, 100) };
  }
  return series;
}

/**
 * Map raw model events to the Event shape used by the rest of the app.
 * Clamps out-of-bounds values and drops any with an unrecognized tag
 * (schema enforcement is belt-and-braces: the API enforces it already).
 */
function normalizeModelEvents(raw: ModelEvent[]): Event[] {
  const result: Event[] = [];
  raw.forEach((e, i) => {
    const tag = VALID_TAGS.includes(e.tag as (typeof VALID_TAGS)[number])
      ? e.tag
      : "flat"; // Schema prevents this, but be defensive.
    result.push({
      id: i,
      text: String(e.text ?? "").slice(0, 240),
      delta: clamp(Number(e.delta) || 0, DELTA_MIN, DELTA_MAX),
      tag,
      cert: clamp(Number(e.cert) || 0, CERT_MIN, CERT_MAX),
      time: Math.round(clamp(Number(e.time) || 0, TIME_MIN, TIME_MAX)),
    });
  });
  // Sort so the integration loop sees events in time order. The
  // regex engine does the same sort before integration.
  result.sort((a, b) => a.time - b.time);
  // Re-index so `id` matches the sorted order — the integration loop
  // and downstream UI use `id` as a stable key.
  result.forEach((e, i) => {
    e.id = i;
  });
  return result;
}

/**
 * Call Claude Sonnet 4.6 via raw fetch.
 *
 * Returns `null` when: no API key is configured, the request times
 * out, the HTTP response is an error, the body can't be parsed, or
 * the returned tool_use payload doesn't match our schema. In every
 * one of those cases the caller falls back to regex.
 *
 * The AbortController gives us a hard wall-clock timeout; note that
 * `fetch` in Node treats AbortError as a rejection we catch below.
 */
async function tryClaudeParse(
  text: string,
): Promise<{ events: Event[]; series: Point[] } | null> {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  // Fast-path fail if the key is unset. `trim()` guards against a key
  // that got set to the empty string by `.env.local` being checked in
  // with a blank value — common footgun.
  if (!apiKey || !apiKey.trim()) return null;

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), CLAUDE_TIMEOUT_MS);

  try {
    const body = {
      model: CLAUDE_MODEL,
      max_tokens: 2048,
      // System prompt with prompt caching. `cache_control: ephemeral`
      // on the last system block caches both tools + system together
      // (render order is tools -> system -> messages). On repeat
      // requests this reads at ~0.1x input cost instead of full.
      system: [
        {
          type: "text",
          text: SYSTEM_PROMPT,
          cache_control: { type: "ephemeral" },
        },
      ],
      tools: [TOOL_SCHEMA],
      // Force the model to emit our tool rather than a free-form
      // reply. Sonnet 4.6 supports the `tool` forced-choice form.
      tool_choice: { type: "tool", name: TOOL_SCHEMA.name },
      messages: [
        {
          role: "user",
          content: [
            {
              type: "text",
              // The narrative text is the only volatile part of the
              // request; everything above is stable and cacheable.
              text: `Narrative:\n\n${text}`,
            },
          ],
        },
      ],
    };

    const res = await fetch(ANTHROPIC_MESSAGES_URL, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-api-key": apiKey,
        "anthropic-version": ANTHROPIC_VERSION,
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    if (!res.ok) {
      // Any non-2xx (401, 429, 500, etc.) — fall back. We intentionally
      // don't surface the error to the client; the caller should always
      // get a usable response.
      return null;
    }

    const payload = (await res.json()) as {
      content?: Array<{
        type: string;
        name?: string;
        input?: unknown;
      }>;
    };

    // Walk the content blocks looking for our tool_use. Claude may
    // interleave text blocks before / after, and we only care about
    // the tool call payload.
    const toolBlock = payload.content?.find(
      (b) => b.type === "tool_use" && b.name === TOOL_SCHEMA.name,
    );
    if (!toolBlock || !toolBlock.input) return null;

    // Validate shape. Malformed = fall back. The API's strict-schema
    // enforcement should make this unreachable in practice, but we
    // still parse defensively because a model refusal can surface as
    // an unexpected structure.
    const parsed = ModelOutputSchema.safeParse(toolBlock.input);
    if (!parsed.success) return null;

    const events = normalizeModelEvents(parsed.data.events);
    const baseline = clamp(
      typeof parsed.data.baseline === "number" ? parsed.data.baseline : 50,
      0,
      100,
    );
    const series = integrateSeries(events, baseline);
    return { events, series };
  } catch {
    // AbortError (timeout), network error, JSON parse error — any of
    // them puts us on the regex path. We intentionally swallow the
    // error; the route's contract is "always respond usefully."
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

/**
 * POST handler. Always responds with a valid payload; errors only on
 * a genuinely malformed request body.
 */
export async function POST(request: NextRequest) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { error: "Invalid JSON body." },
      { status: 400 },
    );
  }

  const parsed = RequestSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Request body must be { text: string }." },
      { status: 400 },
    );
  }

  const text = parsed.data.text;

  // Short-circuit empty input: no point calling Claude, and the regex
  // engine's emptySeries() already handles this.
  if (!text.trim()) {
    const { events, series } = parseNarrative("");
    return NextResponse.json(
      { events, series, source: "regex" as const },
      { headers: { "Cache-Control": "no-store" } },
    );
  }

  const claudeResult = await tryClaudeParse(text);
  if (claudeResult) {
    return NextResponse.json(
      {
        events: claudeResult.events,
        series: claudeResult.series,
        source: "claude" as const,
      },
      { headers: { "Cache-Control": "no-store" } },
    );
  }

  // Fallback: regex engine. Synchronous, fast, deterministic.
  const { events, series } = parseNarrative(text);
  return NextResponse.json(
    { events, series, source: "regex" as const },
    { headers: { "Cache-Control": "no-store" } },
  );
}
