# Pattern-Based Forecasting, Confidence Scoring, and Backtesting

## 1. Analog-Based Forecasting

### Historical Analog Methods

Analog forecasting matches current patterns to similar historical periods, using subsequent trajectories to form probabilistic forecasts. Originating in meteorology (3-5 close analogs per year), it has been applied to financial markets via DTW, matrix profile, and other similarity measures.

Modern enhancements:
- **Learned spatial masks**: ML-optimized weighting of features for analog selection (Rader et al. 2023)
- **Deep learning analog selection**: Neural networks for extreme event analog identification

### Similar Pattern Search for Stock Prediction

- **DTW-based**: Dominant similarity measure. Flexibly aligns sequences with temporal shifts. Applications: stock clustering, pattern mining, inter-market dynamics
- **PIP + DTW**: Perceptually Important Points for segmentation, then DTW for matching
- **Matrix Profile / STUMPY**: Parameter-free nearest-neighbor for every subsequence. Motif discovery, discord detection, time series chains
- **Template vs. rule-based**: Template matching uses chart similarity; rule-based uses mathematical algorithms

### Confidence Scoring

Composite weighted scoring frameworks:
- **Pattern geometric fit**: ~40% weight (how closely pattern matches)
- **Volume confirmation**: ~30% weight (whether volume supports pattern)
- **Trend/market regime alignment**: ~30% weight

JP Morgan's research: "first steps towards data-driven technical analysis" for searching patterns in daily stock data.

## 2. Forecast Cone / Fan Chart Generation

### Percentile-Based Projection

Fan charts (popularized by Bank of England, 1990s) display forecast uncertainty. Typical bands: 50%, 75%, 90% confidence intervals.

**Procedure for analog-based forecasting:**
1. Identify top-N most similar historical patterns
2. Extract subsequent trajectories of each analog
3. At each future time step, compute percentiles (10th, 25th, 50th, 75th, 90th)
4. Visualize as nested shaded bands

**ECB Fan Charts 2.0**: Flexible forecast distributions incorporating expert judgment, allowing skewed and fat-tailed uncertainty bands.

For asymmetric distributions: center fan at mode (most likely) and use Highest Probability Density (HPD) ranges.

### Confidence Decay

Prediction intervals widen with forecast horizon as uncertainty compounds. Standard deviation sigma_h usually increases with horizon h.

Examples:
- NHC hurricane cone: circle sizes set so 2/3 of historical errors fall within
- RBA: bands = median +/- average historical RMSEs at each horizon

### Calibration

A calibrated (1-alpha) interval should contain the true value with probability (1-alpha).

**Key finding: Almost all prediction intervals are too narrow.** Nominal 95% intervals often achieve only 71-87% empirical coverage.

- **Unconditional calibration**: marginal coverage matches nominal level
- **Conditional calibration**: coverage correct across different conditions/regimes
- **Interval Score**: proper scoring rule decomposable into calibration + sharpness

## 3. Backtesting Strategies

### Walk-Forward Validation (WFA)

Gold standard for backtesting. Unlike single train/test split, WFA uses rolling windows:
1. Optimize on training set
2. Test on subsequent period
3. Roll forward and repeat

**Benchmarks:**
- Walk-Forward Efficiency < 35%: suggests curve-fitting
- 50-85%: strong potential
- Professional-grade: profitable in 70%+ of out-of-sample windows

### Calibration Curves

**Brier Score** decomposes into:
- **Reliability (calibration)**: predicted probabilities match observed frequencies
- **Resolution**: predictions differ from base rate
- **Uncertainty**: inherent outcome variability

**Reliability diagrams**: plot predicted vs observed frequencies. Perfect calibration = diagonal.

### Error Metrics for Pattern-Matching

- **Directional accuracy (hit rate)**: % of correct direction predictions
- **RMSE / MAE**: standard error metrics
- **Sharpe ratio / profit factor**: risk-adjusted returns
- **Coverage probability**: % of actuals within predicted intervals
- **Interval Score**: calibration + sharpness combined

## 4. Commercial Pattern Matching Tools

### TrendSpider
Most advanced automated platform. AI-powered chart pattern detection (triangles, flags, channels, wedges), automated trendlines, Fibonacci, candlestick recognition, code-free backtesting.

### TradingView
Pattern recognition via community Pine Script indicators. Premium ($56/mo) includes some automated recognition. Strong community ecosystem.

### ThinkOrSwim (Charles Schwab)
Professional-grade platform. Less automated pattern recognition; stronger for execution and options.

### Others
- **Trade Ideas**: AI-powered scanning and signal generation
- **Patternz**: Free desktop pattern finder
- **PatternExplorer**: Dedicated pattern exploration
- **Timing Solution**: Academic/scientific standards for pattern research
- **YOLOv8 Stock Pattern Detection**: Computer vision for chart pattern detection on HuggingFace

### Key Differentiator of This Project

Most commercial tools focus on classical chart patterns (head & shoulders, triangles, etc.). **The Similarity** differs fundamentally by:
- Using arbitrary subsequence similarity, not predefined templates
- Employing multiple mathematical distance measures (DTW, Koopman, TDA, etc.)
- Generating probabilistic forecasts from matched historical outcomes
- Providing composite confidence scores from 9 independent methods

## 5. State of the Art in Similarity Search (2024-2026)

### Time Series Foundation Models

Major wave in 2024-2025:
- **TimesFM (Google, ICML 2024)**: Decoder-only, state-of-the-art zero-shot forecasting
- **Chronos-2 (Amazon)**: Based on T5, 300+ forecasts/second on single GPU
- **Moirai (Salesforce)**, **TimeGPT (Nixtla)**, **Lag-Llama (ServiceNow)**
- **Kronos**: Financial-specific, pre-trained on 12B K-line records from 45 exchanges

**Critical finding**: Off-the-shelf foundation models perform weakly for zero-shot financial forecasting, underperforming CatBoost/LightGBM. Fine-tuning yields limited improvements. Domain-specific architectures outperform generic models on financial data.

### Neural Approaches and Learned Embeddings

- **CNN + RNN hybrids**: Highest accuracies for similarity/classification
- **Transformer-based**: PMANet for stock prediction
- **Text embeddings for time series (LETS-C)**: Language model embeddings (e.g., OpenAI text-embedding-3-large) for classification
- **Vector databases**: Pinecone for time series vectorization and similarity search at scale

### Hybrid Traditional + ML

- Matrix Profile + Deep Learning for downstream tasks
- DTW distance matrices + clustering/classification models
- SAX-based indexes for similarity search
- Attention + chart patterns for market movement prediction

### Key Limitations

Research indicates historic prices alone are insufficient for reliable trend prediction without information about other market participants. Simple pattern-based approaches face the challenge that patterns "are insufficient to provide a reliable prediction and are more likely to happen randomly." This underscores the need for rigorous backtesting, calibration, and multi-signal approaches.

## References

- [Analog Forecasting (World Climate Service)](https://www.worldclimateservice.com/2021/09/02/what-is-analog-forecasting/)
- [ML Boosts Analog Forecasting (Penn State)](https://www.psu.edu/news/earth-and-mineral-sciences/story/machine-learning-technology-boosts-analog-weather-forecasting)
- [DTW in Quantitative Trading (Alphanome)](https://www.alphanome.ai/post/dynamic-time-warping-in-quantitative-trading)
- [JP Morgan: Searching for Patterns](https://www.jpmorgan.com/technology/technology-blog/searching-for-patterns)
- [Fan Chart (Wikipedia)](https://en.wikipedia.org/wiki/Fan_chart_(time_series))
- [ECB Fan Charts 2.0](https://www.ecb.europa.eu/pub/pdf/scpwps/ecb.wp2624~4e679bae9b.en.pdf)
- [Fan Charts from Historical Errors (RBA)](https://www.rba.gov.au/publications/rdp/2017/2017-01/fan-charts.html)
- [Prediction Intervals (FPP 3rd ed.)](https://otexts.com/fpp3/prediction-intervals.html)
- [Walk-Forward Analysis (Surmount AI)](https://surmount.ai/blogs/walk-forward-analysis-vs-backtesting-pros-cons-best-practices)
- [Walk-Forward Optimization (QuantInsti)](https://blog.quantinsti.com/walk-forward-optimization-introduction/)
- [Stable Reliability Diagrams (PNAS)](https://www.pnas.org/doi/10.1073/pnas.2016191118)
- [TrendSpider](https://trendspider.com/)
- [TimesFM (Google Research)](https://github.com/google-research/timesfm)
- [Kronos Financial Foundation Model](https://jonathankinlay.com/2026/02/time-series-foundation-models-for-financial-markets-kronos-and-the-rise-of-pre-trained-market-models/)
- [Foundation Models in Finance (arXiv)](https://arxiv.org/html/2511.18578v1)
- [Stock Market Trend Prediction Limitations (Nature)](https://www.nature.com/articles/s41599-025-04761-8)
