/**
 * /api/narrative — stub endpoint for narrative-to-trajectory compilation.
 *
 * Accepts a POST with a JSON body `{ text: string }` containing a
 * natural-language narrative describing market/world events. Returns
 * mock data representing:
 *   - parsed events extracted from the narrative
 *   - a synthetic trajectory (array of numbers) implied by those events
 *   - a list of similar historical patterns from the engine
 *
 * This is a stub — the real implementation will call the NL-to-timeseries
 * pipeline in the_similarity engine. The mock data is deterministic so
 * the UI can be developed and tested without a running backend.
 */

import { NextRequest, NextResponse } from "next/server";

/** A single event parsed from the narrative text. */
interface ParsedEvent {
  /** Zero-based index in the narrative's event sequence. */
  index: number;
  /** Short label summarizing the event. */
  label: string;
  /** Estimated directional impact on the trajectory. */
  impact: "positive" | "negative" | "neutral";
  /** Approximate magnitude of the move (0-1 scale). */
  magnitude: number;
}

/** A historical pattern that resembles the compiled trajectory. */
interface SimilarHistory {
  /** Human-readable label for the historical period. */
  label: string;
  /** Similarity score (0-1, higher = more similar). */
  score: number;
  /** Date range string for display. */
  period: string;
}

/** Full response payload from the narrative compilation endpoint. */
interface NarrativeResponse {
  /** Events extracted from the input text. */
  events: ParsedEvent[];
  /** Synthetic trajectory implied by the parsed events. */
  trajectory: number[];
  /** Historical patterns similar to the compiled trajectory. */
  similarHistories: SimilarHistory[];
}

/**
 * Generate deterministic mock data from the input narrative text.
 *
 * The trajectory shape is derived from a simple hash of the input so
 * the same text always produces the same chart — useful for UI development.
 */
function compileMock(text: string): NarrativeResponse {
  // Simple hash to seed deterministic output.
  let hash = 0;
  for (let i = 0; i < text.length; i++) {
    hash = ((hash << 5) - hash + text.charCodeAt(i)) | 0;
  }
  const seed = Math.abs(hash);

  // Parse mock events from sentence boundaries.
  const sentences = text
    .split(/[.!?]+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 3);

  const impacts: Array<"positive" | "negative" | "neutral"> = [
    "positive",
    "negative",
    "neutral",
  ];

  const events: ParsedEvent[] = sentences.slice(0, 8).map((sentence, i) => ({
    index: i,
    label: sentence.length > 60 ? sentence.slice(0, 57) + "..." : sentence,
    impact: impacts[(seed + i) % 3],
    magnitude: 0.2 + ((seed * (i + 1)) % 80) / 100,
  }));

  // Build a trajectory: start at 100 and walk based on events.
  const trajectoryLen = Math.max(events.length * 5, 20);
  const trajectory: number[] = [100];
  for (let i = 1; i < trajectoryLen; i++) {
    const eventIdx = Math.floor((i / trajectoryLen) * events.length);
    const event = events[Math.min(eventIdx, events.length - 1)];
    const direction =
      event.impact === "positive" ? 1 : event.impact === "negative" ? -1 : 0;
    // Small random-looking walk seeded by hash + index.
    const noise = (((seed * (i + 7)) % 100) - 50) / 200;
    const step = direction * event.magnitude * 0.8 + noise;
    trajectory.push(trajectory[i - 1] + step);
  }

  const similarHistories: SimilarHistory[] = [
    { label: "2008 Financial Crisis", score: 0.87, period: "Sep 2008 - Mar 2009" },
    { label: "COVID-19 Crash & Recovery", score: 0.82, period: "Feb 2020 - Aug 2020" },
    { label: "Dot-com Bubble Burst", score: 0.74, period: "Mar 2000 - Oct 2002" },
    { label: "2022 Rate Hike Cycle", score: 0.69, period: "Jan 2022 - Oct 2022" },
    { label: "Brexit Referendum", score: 0.61, period: "Jun 2016 - Dec 2016" },
  ];

  return { events, trajectory, similarHistories };
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const text: string = body?.text ?? "";

    if (!text.trim()) {
      return NextResponse.json(
        { error: "Narrative text is required." },
        { status: 400 },
      );
    }

    // Simulate a small processing delay so the UI loading state is visible.
    await new Promise((resolve) => setTimeout(resolve, 600));

    const result = compileMock(text);

    return NextResponse.json(result, {
      headers: {
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return NextResponse.json(
      { error: "Failed to parse request body." },
      { status: 400 },
    );
  }
}
