# JEPA data representation

First-pass data representation for training a Joint Embedding Predictive Architecture (JEPA) on The Similarity's financial time series datasets.

## What representation was chosen and why

| Dimension | Choice | Rationale |
|-----------|--------|-----------|
| **Primary signal** | Normalized log-returns `ln(p[t]/p[t-1])` | Scale-invariant (a 10% move looks the same on a $10 stock and a $1000 stock), approximately stationary, and matches the production matcher's default `logreturn_zscore` normalization. Raw prices are non-stationary and vary across orders of magnitude. |
| **Per-window normalization** | Z-score (zero mean, unit variance) per window | Removes remaining location/scale differences. Per-window (not global) so no future information leaks into past windows. Consistent with `the_similarity/core/normalizer.py`. |
| **Window size** | 60 bars | Production default. Keeps JEPA embeddings directly comparable to matcher query windows without interpolation. |
| **Optional channel: volatility** | Rolling std of log-returns (lookback=20) | Captures the *texture* of price movement (calm rally vs choppy rally). 20-bar lookback approximates one trading month at daily frequency. |
| **Optional channel: volume** | Z-scored per window | Adds market participation context when available. Not all datasets include volume. |
| **Tensor shape** | `(n_windows, n_channels, window_size)` | Standard "channels-first" layout compatible with PyTorch Conv1d and typical JEPA encoder architectures. |

## Train / val / test split policy

**Strictly temporal, no shuffling.** Financial time series are serially correlated — random shuffling creates look-ahead bias.

| Split | Fraction | Purpose |
|-------|----------|---------|
| Train | 70% | Model training |
| Val | 15% | Hyperparameter tuning, early stopping |
| Test | 15% | Final evaluation (touched once) |

Fractions are applied to the *window count*. All train windows come before all val windows, and all val windows come before all test windows. No window appears in more than one split.

## Known leakage risks and mitigations

1. **Overlapping windows within a split.** With stride=1, consecutive windows share 59 of 60 bars. This is acceptable *within* a split (the model must generalize to unseen positions), but windows straddling a split boundary would leak. **Mitigation:** Each window is assigned entirely to one split based on its start index. No window crosses a boundary.

2. **Global normalization statistics.** If we computed a global mean/std across the entire dataset, future data would influence training windows. **Mitigation:** Z-score normalization uses only the bars *within each window*. No global stats are computed.

3. **Cross-dataset leakage.** If training on multiple assets, asset A's test period might temporally overlap with asset B's training period. **Mitigation:** When combining datasets, use a common calendar-date cutoff (not per-asset percentile splits).

4. **Target leakage in self-supervised training.** In JEPA, the model predicts embeddings of a "target" sub-window from a "context" sub-window. Both come from the same window, so no *temporal* leakage occurs. However, if the masking strategy is predictable, the model can shortcut. **Mitigation:** Randomize mask positions during training.

## Implementation

- Code: `research/autoresearch/scripts/jepa_data_spec.py`
- Tests: `research/autoresearch/scripts/test_jepa_data_spec.py`
- Production normalizer it mirrors: `the_similarity/core/normalizer.py`
- Production windower it mirrors: `the_similarity/core/windower.py`

## Links

- [[Nine-method pipeline]] — the production matcher that JEPA embeddings will eventually feed into
- [[Engine map]] — where normalizer and windower live
- [[Research hub]] — broader research context
