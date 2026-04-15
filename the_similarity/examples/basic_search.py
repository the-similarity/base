"""Basic The Similarity usage example with synthetic data."""

import numpy as np
import the_similarity


def main():
    # Generate synthetic price data with repeating patterns
    np.random.seed(42)
    t = np.linspace(0, 20 * np.pi, 2000)
    price = 100 + 10 * np.sin(t) + 5 * np.sin(3 * t) + np.random.randn(2000) * 2
    price = np.cumsum(np.abs(np.diff(price)) * np.sign(np.diff(price))) + 100

    # Load as TimeSeries
    history = the_similarity.load(price)

    # Use last 100 bars as query
    query_values = price[-150:-50]
    query = the_similarity.load(query_values)

    # Search for similar patterns
    print("Searching for similar patterns...")
    results = the_similarity.search(
        query=query,
        history=history,
        top_k=10,
        stride=5,  # speed up by skipping every 5 bars
    )

    print(f"Found {len(results.matches)} matches\n")
    for i, match in enumerate(results.matches[:5]):
        print(f"Match #{i + 1}:")
        print(f"  Position: [{match.start_idx}:{match.end_idx}]")
        print(f"  Confidence: {match.confidence_score:.1f}/100")
        print(f"  DTW score: {match.score_breakdown.dtw:.3f}")
        print(f"  Pearson:   {match.score_breakdown.pearson_warped:.3f}")
        print()

    # Project forward
    forecast = the_similarity.project(results, history, forward_bars=30)
    print("Forecast percentiles at bar 30:")
    for p, curve in forecast.curves.items():
        print(f"  P{p}: {curve[-1]:+.4f} ({curve[-1] * 100:+.2f}%)")

    # Plot (comment out if running headless)
    # the_similarity.plot(results, forecast, top_n=5)


if __name__ == "__main__":
    main()
