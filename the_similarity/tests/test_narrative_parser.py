"""
Tests for the narrative schema contracts and rule-based parser.

Covers:
- Event type extraction from keyword matching
- Intensity modifier detection
- Duration extraction from time phrases
- Multi-event sequence parsing with transitions
- Serialization round-trip (to_dict / from_dict)
- Edge cases: empty input, no matches, clamping
- Sharpness extraction for transitions
"""

import json
import os

import pytest

from the_similarity.narrative.contracts import (
    NarrativeEvent,
    NarrativeSequence,
    NarrativeTransition,
    NarrativeType,
)
from the_similarity.narrative.parser import parse_narrative


class TestNarrativeEventTypeExtraction:
    """Verify that the parser maps keywords to the correct NarrativeType."""

    @pytest.mark.parametrize(
        "text, expected_type",
        [
            ("The market crashed.", NarrativeType.CRASH),
            ("Prices plummeted overnight.", NarrativeType.CRASH),
            ("A massive sell-off occurred.", NarrativeType.CRASH),
            ("The stock rallied hard.", NarrativeType.RALLY),
            ("Equities climbed steadily.", NarrativeType.RALLY),
            ("The market consolidated.", NarrativeType.CONSOLIDATION),
            ("Trading went sideways.", NarrativeType.CONSOLIDATION),
            ("It broke out above resistance.", NarrativeType.BREAKOUT),
            ("The trend reversed.", NarrativeType.REVERSAL),
            ("Prices drifted lower.", NarrativeType.DRIFT),
            ("The asset spiked.", NarrativeType.SPIKE),
            ("It mean-reverted over a week.", NarrativeType.MEAN_REVERSION),
        ],
    )
    def test_single_event_type(self, text: str, expected_type: NarrativeType) -> None:
        """Each keyword phrase should map to exactly one event type."""
        result = parse_narrative(text)
        assert len(result.events) == 1, f"Expected 1 event, got {len(result.events)}"
        assert result.events[0].event_type == expected_type


class TestIntensityModifiers:
    """Verify that intensity modifiers are detected and applied."""

    def test_sharp_modifier(self) -> None:
        """'sharply' should yield intensity ~0.8."""
        result = parse_narrative("The market crashed sharply.")
        assert result.events[0].intensity == pytest.approx(0.8, abs=0.05)

    def test_slight_modifier(self) -> None:
        """'slightly' should yield intensity ~0.3."""
        result = parse_narrative("Prices drifted slightly higher.")
        assert result.events[0].intensity == pytest.approx(0.3, abs=0.05)

    def test_no_modifier_default(self) -> None:
        """No modifier should yield default intensity of 0.5."""
        result = parse_narrative("The stock rallied.")
        assert result.events[0].intensity == pytest.approx(0.5, abs=0.05)

    def test_extreme_modifier(self) -> None:
        """'catastrophically' should yield intensity ~1.0."""
        result = parse_narrative("The fund collapsed catastrophically.")
        assert result.events[0].intensity == pytest.approx(1.0, abs=0.05)


class TestDurationExtraction:
    """Verify that duration is extracted from time phrases."""

    def test_duration_days(self) -> None:
        """'for 3 days' should set duration_bars to 3."""
        result = parse_narrative("The market crashed for 3 days.")
        assert result.events[0].duration_bars == 3

    def test_duration_sessions(self) -> None:
        """'over 5 sessions' should set duration_bars to 5."""
        result = parse_narrative("Prices consolidated over 5 sessions.")
        assert result.events[0].duration_bars == 5

    def test_no_duration_default(self) -> None:
        """No time phrase should default to duration_bars = 1."""
        result = parse_narrative("The stock spiked.")
        assert result.events[0].duration_bars == 1


class TestMultiEventSequences:
    """Verify that multi-sentence narratives produce ordered event sequences."""

    def test_three_event_sequence(self) -> None:
        """A three-phase narrative should produce 3 events and 2 transitions."""
        text = (
            "The market crashed for 5 days. "
            "Then it consolidated for 2 weeks. "
            "Finally it rallied."
        )
        result = parse_narrative(text)
        assert len(result.events) == 3
        assert result.events[0].event_type == NarrativeType.CRASH
        assert result.events[1].event_type == NarrativeType.CONSOLIDATION
        assert result.events[2].event_type == NarrativeType.RALLY
        # Transitions
        assert len(result.transitions) == 2
        assert result.transitions[0].from_event == NarrativeType.CRASH
        assert result.transitions[0].to_event == NarrativeType.CONSOLIDATION
        assert result.transitions[1].from_event == NarrativeType.CONSOLIDATION
        assert result.transitions[1].to_event == NarrativeType.RALLY

    def test_semicolon_delimiter(self) -> None:
        """Semicolons should also delimit events."""
        text = "The stock spiked; then it reversed."
        result = parse_narrative(text)
        assert len(result.events) == 2
        assert result.events[0].event_type == NarrativeType.SPIKE
        assert result.events[1].event_type == NarrativeType.REVERSAL


class TestSerialization:
    """Verify to_dict / from_dict round-trip for all contracts."""

    def test_event_round_trip(self) -> None:
        """NarrativeEvent should survive a to_dict -> from_dict round-trip."""
        event = NarrativeEvent(
            event_type=NarrativeType.CRASH,
            intensity=0.8,
            duration_bars=5,
            description="It crashed.",
        )
        restored = NarrativeEvent.from_dict(event.to_dict())
        assert restored.event_type == event.event_type
        assert restored.intensity == event.intensity
        assert restored.duration_bars == event.duration_bars
        assert restored.description == event.description

    def test_transition_round_trip(self) -> None:
        """NarrativeTransition should survive a to_dict -> from_dict round-trip."""
        transition = NarrativeTransition(
            from_event=NarrativeType.CRASH,
            to_event=NarrativeType.RALLY,
            trigger="Fed cut rates",
            sharpness=0.9,
        )
        restored = NarrativeTransition.from_dict(transition.to_dict())
        assert restored.from_event == transition.from_event
        assert restored.to_event == transition.to_event
        assert restored.trigger == transition.trigger
        assert restored.sharpness == transition.sharpness

    def test_sequence_round_trip(self) -> None:
        """Full NarrativeSequence should survive serialization."""
        text = "The market crashed sharply for 3 days. Then it rallied."
        original = parse_narrative(text)
        restored = NarrativeSequence.from_dict(original.to_dict())
        assert len(restored.events) == len(original.events)
        assert len(restored.transitions) == len(original.transitions)
        assert restored.source_text == original.source_text
        assert restored.metadata == original.metadata
        for orig_e, rest_e in zip(original.events, restored.events):
            assert orig_e.event_type == rest_e.event_type
            assert orig_e.intensity == rest_e.intensity


class TestEdgeCases:
    """Edge cases: empty input, no matches, intensity clamping."""

    def test_empty_string(self) -> None:
        """Empty string should return empty sequence."""
        result = parse_narrative("")
        assert len(result.events) == 0
        assert len(result.transitions) == 0

    def test_no_keywords(self) -> None:
        """Text with no event keywords should return empty events list."""
        result = parse_narrative("The weather was nice today.")
        assert len(result.events) == 0

    def test_intensity_clamping(self) -> None:
        """Intensity should be clamped to [0, 1]."""
        event = NarrativeEvent(event_type=NarrativeType.CRASH, intensity=1.5)
        assert event.intensity == 1.0
        event2 = NarrativeEvent(event_type=NarrativeType.CRASH, intensity=-0.5)
        assert event2.intensity == 0.0

    def test_duration_minimum(self) -> None:
        """duration_bars should always be >= 1."""
        event = NarrativeEvent(event_type=NarrativeType.CRASH, duration_bars=0)
        assert event.duration_bars == 1

    def test_source_text_preserved(self) -> None:
        """The original text should be preserved in the sequence."""
        text = "The market rallied."
        result = parse_narrative(text)
        assert result.source_text == text


class TestSharpnessExtraction:
    """Verify sharpness is extracted for transitions."""

    def test_sudden_transition(self) -> None:
        """'suddenly' in the second event sentence should yield high sharpness."""
        text = "The market consolidated. Suddenly it broke out."
        result = parse_narrative(text)
        assert len(result.transitions) == 1
        assert result.transitions[0].sharpness >= 0.8

    def test_gradual_transition(self) -> None:
        """'gradually' should yield low sharpness."""
        text = "Prices spiked. The asset gradually mean-reverted."
        result = parse_narrative(text)
        assert len(result.transitions) == 1
        assert result.transitions[0].sharpness <= 0.3


class TestExampleNarratives:
    """Validate parser against the example narratives JSON fixture."""

    @pytest.fixture
    def examples(self) -> list:
        """Load the example narratives from the data directory."""
        data_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "narrative",
            "data",
            "example_narratives.json",
        )
        with open(data_path) as f:
            return json.load(f)

    def test_example_event_counts(self, examples: list) -> None:
        """Each example should produce the expected number of events."""
        for ex in examples:
            result = parse_narrative(ex["text"])
            expected_count = len(ex["expected_events"])
            assert len(result.events) == expected_count, (
                f"Example '{ex['id']}': expected {expected_count} events, "
                f"got {len(result.events)}"
            )

    def test_example_event_types(self, examples: list) -> None:
        """Each example should produce events with the correct types."""
        for ex in examples:
            result = parse_narrative(ex["text"])
            for i, (actual, expected) in enumerate(
                zip(result.events, ex["expected_events"])
            ):
                assert actual.event_type.value == expected["event_type"], (
                    f"Example '{ex['id']}' event {i}: expected "
                    f"{expected['event_type']}, got {actual.event_type.value}"
                )
