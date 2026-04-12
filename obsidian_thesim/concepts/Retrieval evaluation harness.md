# Retrieval evaluation harness

A reusable framework for comparing any experimental retrieval function against the production baseline (`the_similarity.api.search`).

## Location

`research/autoresearch/scripts/retrieval_harness.py`

## Purpose

Before wiring any experimental retriever (e.g. JEPA embeddings) into the production [[Nine-method pipeline]], we need reproducible evidence that it improves retrieval quality.  The harness provides that evidence in two modes:

1. **Set comparison** (`run_comparison`) — given the same queries, how much do the two retrievers agree?
2. **Walk-forward evaluation** (`compare_walk_forward`) — with no-lookahead, whose top-k matches have better forward predictive power?

## Metrics

| Metric | What it measures | Ideal |
|--------|-----------------|-------|
| `top_k_overlap` | Jaccard similarity of top-k offset sets | descriptive |
| `rank_correlation` | Spearman rho over shared results | descriptive |
| `rank_lift` | Per-result signed rank change (positive = experimental ranked higher) | higher is better |
| `recall_at_k` | Fraction of baseline top-k appearing in experimental top-k | descriptive |
| `mean_abs_forward` | Mean absolute forward return of matched windows (walk-forward mode) | lower = more predictive |

## Protocol

```python
from research.autoresearch.scripts.retrieval_harness import (
    RetrievalHarness, RetrievalResult
)

def my_experimental_retriever(query, history, k):
    # ... return list[RetrievalResult] ...
    pass

harness = RetrievalHarness(baseline_fn, my_experimental_retriever)
report = harness.run_comparison(dataset, query_windows, k=10)
harness.generate_report("report.json")
```

## CLI

```bash
python research/autoresearch/scripts/retrieval_harness.py \
    --dataset spy --k 10 --output report.json
```

## Relationship to benchmark

The harness is designed to produce the retrieval metrics referenced in `research/autoresearch/benchmarks/jepa-retrieval-core-v1.yaml` — specifically `top_k_overlap_vs_baseline` and `rank_lift_for_known_good_matches`.

## Tests

31 tests in `research/autoresearch/scripts/test_retrieval_harness.py` covering metric math, mock retrievers, walk-forward no-lookahead enforcement, and report serialization.

## See also

- [[Nine-method pipeline]] — the production retrieval engine
- [[Engine map]] — code paths for `the_similarity/core/matcher.py`
- [[Repo research and docs]] — research directory layout
