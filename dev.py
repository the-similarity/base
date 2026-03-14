"""Quick smoke test — run the full 9-method pipeline on real data."""
import time
from the_similarity import api
from the_similarity.config import Config

# Load BTC daily
ts = api.load("the-similarity-data/data/crypto/btc_usdt/1d.parquet")
print(f"Loaded {len(ts.values)} bars of BTC/USDT daily")

# Use last 60 bars as query, rest as history
query = ts[-60:]
history = ts

# Full pipeline — all 9 methods active, tier2=10 for speed
config = Config(tier2_candidates=10, stride=5)

print(f"\nSearching with {len(config.active_methods)} active methods...")
print(f"  Methods: {config.active_methods}")

t0 = time.time()
results = api.search(query, history, top_k=5, config=config)
elapsed = time.time() - t0

print(f"\nDone in {elapsed:.1f}s")
results.summary()

# Show regime tags
print("\nRegime tags:")
for i, m in enumerate(results.matches[:5]):
    print(f"  #{i+1}  regime={m.regime}  [{m.start_date} → {m.end_date}]")

# Project forward
forecast = api.project(results, history, forward_bars=30)
print(f"\nForecast ({len(forecast.curves)} percentile curves):")
for pct, curve in sorted(forecast.curves.items()):
    print(f"  p{pct}: {curve[-1]:.2f} (30-bar endpoint)")
