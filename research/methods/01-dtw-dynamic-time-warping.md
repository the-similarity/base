# Dynamic Time Warping (DTW) for Financial Time Series Pattern Matching

## 1. Core Algorithm

Dynamic Time Warping is a dynamic programming algorithm that measures similarity between two temporal sequences by non-linearly warping their time axes. Unlike Euclidean distance, which requires point-to-point alignment, DTW finds the optimal alignment between sequences that may vary in speed, phase, or length.

**Algorithm steps:**
1. Construct a cost matrix `D(i,j)` where each cell represents the distance between points `i` and `j` of the two series.
2. Fill the matrix using the recurrence: `D(i,j) = d(x_i, y_j) + min(D(i-1,j), D(i,j-1), D(i-1,j-1))`
3. The optimal warping path is traced back from `D(n,m)` to `D(1,1)`, yielding both the DTW distance and the alignment mapping.

**Complexity:** O(n*m) time and space.

**Key properties:** DTW handles sequences of unequal length, is robust to temporal shifts and dilations, and preserves information about amplitude, trend reversals, and shape.

## 2. Constraint Techniques

### Sakoe-Chiba Band (1978)
Restricts the warping path to a band of width `r` around the diagonal. Only cells within `|i - j| <= r` are computed. Most widely used constraint; generally produces best classification accuracy.

### Itakura Parallelogram (1975)
Constrains the warping path by imposing a maximum slope, creating a parallelogram-shaped region. Generally inferior to Sakoe-Chiba but still superior to unconstrained DTW on most datasets.

### Purpose of Constraints
- **Speed:** Reduces cells computed from O(n^2) to O(n*r)
- **Accuracy:** Prevents "pathological warping" where a small section maps onto a disproportionately large section
- **Best practice:** Optimal window size is data-dependent; cross-validate

## 3. Performance Optimizations

### LB_Keogh Lower Bounding
- Computes in O(n) time by creating upper/lower envelopes around the query
- `U[i] = max(x[i-w : i+w])` and `L[i] = min(x[i-w : i+w])`
- Used to prune candidates: if `LB_Keogh(Q, C) > best_so_far`, skip full DTW
- Not symmetric; LB_Keogh(Q,C) != LB_Keogh(C,Q)

### Other Lower Bounds
- **LB_Improved:** Tighter than LB_Keogh at moderate additional cost
- **LB_Enhanced:** Always tighter than LB_Keogh while being more efficient
- **LB_Petitjean:** Tightest known lower bound computable in linear time

### Early Abandoning
During DTW computation, if accumulated cost exceeds current best-so-far threshold, computation halts early.

### PrunedDTW and EAPrunedDTW
- **PrunedDTW:** Prunes unpromising alignment paths during DTW computation itself
- **EAPrunedDTW:** Combines early abandoning with pruning from the start; can render lower bounding dispensable

### UCR Suite
The landmark "Searching and Mining Trillions of Time Series" work (Rakthanmanon et al., 2012) combined early abandoning of LB_Keogh, early abandoning of DTW, and z-normalization cascading to achieve trillion-scale subsequence search.

## 4. DTW vs Other Distance Measures for Financial Time Series

| Measure | Strengths | Weaknesses |
|---------|-----------|------------|
| **Euclidean** | O(n), simple, fast | No phase tolerance, brittle to temporal shifts |
| **DTW** | Phase-invariant, handles unequal lengths, captures shape | O(n^2) without constraints, parameter tuning needed |
| **Correlation** | Scale-invariant | Only linear relationships, no temporal flexibility |
| **Soft-DTW** | Differentiable, usable as loss in neural networks | Quadratic complexity, smoothing parameter needed |

**For financial time series:**
- DTW excels when comparing patterns with same shape but out of phase (e.g., similar market cycles at different times/speeds)
- Preserves amplitude and trend reversal information that correlation-based measures lose
- Phase-invariance means a quarter-cycle lag won't severely penalize distance
- Applications: business cycle synchronization, sector ETF pattern matching, stock pattern representation

**Caveats:**
- Risk of overfitting when building trading strategies purely on DTW
- Computational demand increases with number of comparisons
- Should be part of a wider toolkit, not relied upon in isolation

## 5. Python Libraries Comparison

### dtaidistance (Recommended for production)
- C-compiled backend with OpenMP parallelization
- Supports full DTW, subsequence search, local concurrences
- `distance_fast` is faster than FastDTW
- Supports distance matrix computation for clustering
- [PyPI](https://pypi.org/project/dtaidistance/) | [Docs](https://dtaidistance.readthedocs.io/en/latest/usage/dtw.html)

### tslearn
- Full DTW (not approximate)
- Integrates with scikit-learn pipelines
- DTW-based clustering (TimeSeriesKMeans), classification (KNN), barycenter averaging (DBA)
- [Docs](https://tslearn.readthedocs.io/en/latest/gen_modules/metrics/tslearn.metrics.dtw.html)

### dtw-python
- Most comprehensive feature set (port of R's DTW package)
- All step patterns classified by Rabiner-Juang, Sakoe-Chiba, Rabiner-Myers
- Arbitrary windowing functions; multivariate alignment
- Best for detailed analysis, not high-throughput search
- [PyPI](https://pypi.org/project/dtw-python/) | [GitHub](https://github.com/DynamicTimeWarping/dtw-python)

### fastdtw (NOT recommended)
- Research demonstrated it is "approximate and generally slower than the algorithm it approximates" (Wu & Keogh, 2020)
- With radius=100, slower than exact DTW for series under ~900 points
- Both original authors and critics recommend constrained exact DTW instead
- [Critique paper](https://arxiv.org/pdf/2003.11246)

### Recommendation
Use **dtaidistance** for high-performance computation, **dtw-python** for detailed alignment analysis, **tslearn** for ML pipelines.

## 6. Recent Developments (2023-2026)

### Soft-DTW and Deep Learning
- **Soft-DTW** (Cuturi & Blondel, 2017): differentiable DTW usable as loss function in neural networks
- **DILATE**: Combines Soft-DTW with temporal distortion index
- **STRIPE** (2023): Extends to probabilistic forecasting
- PyTorch CUDA implementations available for GPU-accelerated Soft-DTW

### Lower Bound Advances
- **LB_Enhanced** and **LB_Petitjean**: current state-of-the-art for linear-time lower bounds
- EAPrunedDTW: effective pruning can make lower bounds dispensable

### Dynamic DTW (SODA 2024)
Theoretical advance addressing "dynamic" variant where sequences are updated incrementally.

### Best Practices Summary
1. Use constrained DTW (Sakoe-Chiba band), not unconstrained or FastDTW. Cross-validate window size.
2. Z-normalize before computing DTW for shape-based comparison.
3. Apply lower bounding (LB_Keogh or LB_Enhanced) before full DTW when searching large datasets.
4. Use dtaidistance with C backend for production performance.
5. Combine DTW with domain knowledge (returns vs prices, smoothing, segmentation).
6. Subsequence DTW is more appropriate than full-sequence DTW for pattern matching.
7. Validate out-of-sample to avoid overfitting.

## References

- [DTW Wikipedia](https://en.wikipedia.org/wiki/Dynamic_time_warping)
- [Pattern Matching Trading System Based on DTW (MDPI)](https://www.mdpi.com/2071-1050/10/12/4641)
- [DTW Constraint Techniques (Tavenard)](https://rtavenar.github.io/hdr/parts/01/dtw.html)
- [Everything You Know About DTW is Wrong (UCR)](https://www.cs.ucr.edu/~eamonn/DTW_myths.pdf)
- [Early Abandoning PrunedDTW (arXiv)](https://arxiv.org/abs/2010.05371)
- [Searching and Mining Trillions of Time Series](https://blog.acolyer.org/2016/05/11/searching-and-mining-trillions-of-time-series-subsequences-under-dynamic-time-warping/)
- [LB_Keogh (UCR)](https://www.cs.ucr.edu/~eamonn/LB_Keogh.htm)
- [Tight Lower Bounds for DTW (arXiv)](https://arxiv.org/pdf/2102.07076)
- [DTW in Quantitative Trading (Alphanome.ai)](https://www.alphanome.ai/post/dynamic-time-warping-in-quantitative-trading)
- [JP Morgan: Searching for Patterns in Stock Data](https://www.jpmorgan.com/technology/technology-blog/searching-for-patterns)
- [FastDTW critique (arXiv)](https://arxiv.org/pdf/2003.11246)
- [Soft-DTW (arXiv)](https://arxiv.org/abs/1703.01541)
- [Dynamic DTW (SODA 2024)](https://epubs.siam.org/doi/10.1137/1.9781611977912.10)
