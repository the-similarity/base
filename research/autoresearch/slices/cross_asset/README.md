# Cross-asset slice pairs

Each YAML file in this directory defines a **pair** of catalogue slices
that observe the same macro event on two different assets. Pairs are used
by cross-asset benchmark lanes (e.g. spillover detection, regime-coherence,
transfer-entropy validation).

## Contract

```yaml
pair_id: <stable kebab-case id, e.g. spy-vs-qqq-covid>
description: 1-line summary
regime_class: crisis | calm | trend | mean_reverting   # inherited from both legs
left:  <catalogue slice id>
right: <catalogue slice id>
join_rule: intersection | union | left_anchor | right_anchor
# intersection:  both legs trimmed to the intersection of their date ranges
# union:         keep full windows, pad missing bars with NaN before join
# left_anchor:   resample right to left's bar timestamps (nearest-bar)
# right_anchor:  resample left to right's bar timestamps (nearest-bar)
notes: free-text, known events across both legs
```

### Why not bar-for-bar alignment?

Calendars differ:
- US equities: 252 trading days/year, no weekends, no holidays
- Crypto: 365 days/year, always-on
- Forex: 5.5 days/week, rolling sessions

Pairs that cross these families **must** use `intersection` or an anchor
join. The runner loads both legs from the catalogue, intersects/anchors
per `join_rule`, and exposes the joined frame to the bench.

### Adding a new pair

1. Both legs must already exist in `../catalogue.yaml`.
2. The `regime_class` of both legs should match; if they differ, document
   the mismatch in `notes`.
3. Date windows must overlap — `validate.py` rejects pairs with empty
   intersections.
4. Like catalogue IDs, `pair_id` is APPEND-ONLY once merged.
