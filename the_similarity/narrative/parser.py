"""
Rule-based narrative parser: free text -> NarrativeSequence.

This is a **baseline** keyword parser, NOT an NLU system. It exists to:
1. Validate the narrative schema end-to-end.
2. Provide a deterministic, dependency-free fallback.
3. Serve as a test oracle for future ML-based parsers.

Algorithm:
    1. Split input text into sentences (period/semicolon/newline delimited).
    2. For each sentence, scan for event-type keywords in priority order.
       The first match wins (one event per sentence).
    3. Scan the same sentence for intensity modifiers and time-duration
       phrases. Apply the strongest modifier found.
    4. Build NarrativeTransition objects between consecutive events.
       Sharpness defaults to 0.5 (unknown); a future version could infer
       sharpness from transition keywords like "suddenly" or "gradually".

Keyword tables are intentionally small and conservative. False negatives
are preferred over false positives — downstream consumers should handle
empty sequences gracefully.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from the_similarity.narrative.contracts import (
    NarrativeEvent,
    NarrativeSequence,
    NarrativeTransition,
    NarrativeType,
)

# ---------------------------------------------------------------------------
# Keyword -> NarrativeType mapping
# ---------------------------------------------------------------------------
# Each entry is (keywords_list, NarrativeType). Order matters: first match
# in a sentence wins. More specific patterns come before generic ones.
# All keywords are matched case-insensitively as whole words.

_EVENT_KEYWORDS: List[Tuple[List[str], NarrativeType]] = [
    # CRASH: sharp downward move
    (
        ["crashed", "crash", "plummeted", "plummeting", "plummet", "collapsed",
         "collapse", "tanked", "tank", "cratered", "crater", "nosedived",
         "nosedive", "free-fell", "free-fall", "sell-off", "selloff"],
        NarrativeType.CRASH,
    ),
    # SPIKE: sudden sharp move (up or down, but typically up in common usage)
    (
        ["spiked", "spike", "surged", "surge", "skyrocketed", "skyrocket",
         "exploded", "explosion", "shot up", "jumped"],
        NarrativeType.SPIKE,
    ),
    # RALLY: sustained upward move
    (
        ["rallied", "rally", "rose", "climbed", "climb", "gained",
         "advanced", "advance", "recovered", "recovery", "bounced",
         "bounce", "soared", "soar"],
        NarrativeType.RALLY,
    ),
    # BREAKOUT: move beyond a range
    (
        ["broke out", "breakout", "break out", "breached", "breach",
         "exceeded", "broke above", "broke below", "broke through"],
        NarrativeType.BREAKOUT,
    ),
    # REVERSAL: direction change
    (
        ["reversed", "reversal", "reverse", "turned around", "turnaround",
         "pivoted", "pivot", "flipped", "flip", "u-turn", "about-face"],
        NarrativeType.REVERSAL,
    ),
    # MEAN_REVERSION: return to average
    (
        ["mean-reverted", "mean reversion", "mean-reversion", "reverted to mean",
         "returned to average", "normalized", "normalize", "regressed to mean",
         "pulled back to", "snapped back"],
        NarrativeType.MEAN_REVERSION,
    ),
    # CONSOLIDATION: sideways / range-bound
    (
        ["consolidated", "consolidation", "consolidate", "flat", "flatlined",
         "range-bound", "rangebound", "sideways", "choppy", "stagnated",
         "stagnant", "traded in a range", "drifted sideways"],
        NarrativeType.CONSOLIDATION,
    ),
    # DRIFT: slow directional move
    (
        ["drifted", "drift", "drifting", "meandered", "meander", "crept",
         "creep", "edged", "inched", "eased", "slid slowly", "grinded"],
        NarrativeType.DRIFT,
    ),
]

# ---------------------------------------------------------------------------
# Intensity modifiers: word -> intensity value
# ---------------------------------------------------------------------------
# Scanned in the same sentence as the event keyword. If multiple modifiers
# appear, the most extreme (furthest from 0.5) wins.

_INTENSITY_MODIFIERS: Dict[str, float] = {
    # Low intensity (0.2 - 0.3)
    "slightly": 0.3,
    "slight": 0.3,
    "marginally": 0.3,
    "modestly": 0.3,
    "mildly": 0.3,
    "gently": 0.3,
    "a bit": 0.3,
    "a little": 0.3,
    "somewhat": 0.35,
    # Medium intensity (0.5 - 0.6) — these are default, listed for explicitness
    "moderately": 0.5,
    "steadily": 0.5,
    # High intensity (0.7 - 0.8)
    "sharply": 0.8,
    "significantly": 0.7,
    "heavily": 0.8,
    "substantially": 0.7,
    "considerably": 0.7,
    "aggressively": 0.8,
    "brutally": 0.9,
    "violently": 0.9,
    "massively": 0.9,
    "dramatically": 0.8,
    "severely": 0.85,
    # Extreme intensity (0.9 - 1.0)
    "catastrophically": 1.0,
    "completely": 1.0,
    "totally": 0.95,
    "historically": 0.9,
    "unprecedented": 0.95,
}

# ---------------------------------------------------------------------------
# Sharpness modifiers for transitions
# ---------------------------------------------------------------------------
_SHARPNESS_KEYWORDS: Dict[str, float] = {
    "suddenly": 0.9,
    "abruptly": 0.9,
    "immediately": 0.95,
    "instantly": 1.0,
    "quickly": 0.8,
    "rapidly": 0.8,
    "gradually": 0.2,
    "slowly": 0.2,
    "eventually": 0.3,
    "over time": 0.3,
    "then": 0.5,
    "before": 0.5,
    "after": 0.5,
}

# ---------------------------------------------------------------------------
# Duration extraction regex
# ---------------------------------------------------------------------------
# Matches phrases like "for 3 days", "over 5 bars", "lasting 2 weeks", etc.
# Captures the numeric value. The time unit is ignored for now — the caller
# must interpret duration_bars in their own timeframe context.

_DURATION_PATTERN = re.compile(
    r"(?:for|over|lasting|lasted|about|around|approximately)\s+"
    r"(\d+)\s+"
    r"(?:day|days|bar|bars|week|weeks|month|months|hour|hours|session|sessions|period|periods)",
    re.IGNORECASE,
)


def _split_sentences(text: str) -> List[str]:
    """
    Split text into sentence-like chunks.

    Uses periods, semicolons, and newlines as delimiters. Strips whitespace
    and drops empty strings. This is intentionally simple — the parser is
    a baseline, not a full NLP pipeline.
    """
    # Replace semicolons and newlines with periods for uniform splitting
    normalized = text.replace(";", ".").replace("\n", ".")
    parts = normalized.split(".")
    return [s.strip() for s in parts if s.strip()]


def _find_event_type(sentence: str) -> Optional[NarrativeType]:
    """
    Scan a sentence for the first matching event-type keyword.

    Returns the NarrativeType if found, None otherwise. Keywords are matched
    case-insensitively. Multi-word keywords (e.g. "broke out") are checked
    via substring match; single-word keywords use word-boundary regex.
    """
    lower = sentence.lower()
    for keywords, event_type in _EVENT_KEYWORDS:
        for kw in keywords:
            if " " in kw:
                # Multi-word: simple substring match
                if kw in lower:
                    return event_type
            else:
                # Single-word: word-boundary match to avoid partial hits
                # e.g. "flatten" should not match "flat" as a standalone word
                pattern = r"\b" + re.escape(kw) + r"\b"
                if re.search(pattern, lower):
                    return event_type
    return None


def _find_intensity(sentence: str) -> float:
    """
    Extract intensity from modifier words in a sentence.

    Returns the modifier value furthest from 0.5 (the default). If no
    modifiers are found, returns 0.5.
    """
    lower = sentence.lower()
    best_intensity = 0.5
    best_distance = 0.0

    for modifier, value in _INTENSITY_MODIFIERS.items():
        if modifier in lower:
            distance = abs(value - 0.5)
            if distance > best_distance:
                best_distance = distance
                best_intensity = value

    return best_intensity


def _find_duration(sentence: str) -> int:
    """
    Extract duration in bars from time phrases.

    Returns the first numeric duration found, or 1 if none.
    """
    match = _DURATION_PATTERN.search(sentence)
    if match:
        return max(1, int(match.group(1)))
    return 1


def _find_sharpness(sentence: str) -> float:
    """
    Extract transition sharpness from keywords in a sentence.

    Returns the sharpness value furthest from 0.5, or 0.5 if none found.
    """
    lower = sentence.lower()
    best_sharpness = 0.5
    best_distance = 0.0

    for keyword, value in _SHARPNESS_KEYWORDS.items():
        if keyword in lower:
            distance = abs(value - 0.5)
            if distance > best_distance:
                best_distance = distance
                best_sharpness = value

    return best_sharpness


def parse_narrative(text: str) -> NarrativeSequence:
    """
    Parse free-text market narrative into a structured NarrativeSequence.

    This is a rule-based keyword parser — a baseline, not NLU. It:
    1. Splits text into sentences.
    2. Extracts one event per sentence (first keyword match wins).
    3. Derives intensity from modifier words.
    4. Extracts duration from time phrases.
    5. Builds transitions between consecutive events.

    Args:
        text: Free-text narrative describing market behavior.
              Example: "The market crashed sharply for 3 days, then
              consolidated before rallying."

    Returns:
        NarrativeSequence with extracted events, transitions, source_text,
        and metadata indicating the parser version. Events list may be
        empty if no keywords are recognized.
    """
    if not text or not text.strip():
        return NarrativeSequence(
            source_text=text or "",
            metadata={"parser": "keyword_v1", "version": "0.1.0"},
        )

    sentences = _split_sentences(text)
    events: List[NarrativeEvent] = []

    for sentence in sentences:
        event_type = _find_event_type(sentence)
        if event_type is None:
            continue

        intensity = _find_intensity(sentence)
        duration = _find_duration(sentence)

        events.append(
            NarrativeEvent(
                event_type=event_type,
                intensity=intensity,
                duration_bars=duration,
                description=sentence,
            )
        )

    # Build transitions between consecutive events.
    # Sharpness is inferred from the description of the *second* event
    # (the sentence that describes the transition destination).
    transitions: List[NarrativeTransition] = []
    for i in range(len(events) - 1):
        sharpness = _find_sharpness(events[i + 1].description)
        transitions.append(
            NarrativeTransition(
                from_event=events[i].event_type,
                to_event=events[i + 1].event_type,
                trigger="",  # Trigger extraction not yet implemented
                sharpness=sharpness,
            )
        )

    return NarrativeSequence(
        events=events,
        transitions=transitions,
        source_text=text,
        metadata={"parser": "keyword_v1", "version": "0.1.0"},
    )
