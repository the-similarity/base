# Survey DTW

**Repo source:** `research/methods/01-dtw-dynamic-time-warping.md`  
**Full write-up in vault:** [[01-dtw-dynamic-time-warping]]

## Friendly summary

Imagine lining up two songs where one band plays **slightly faster**. DTW finds the **best tempo map** so beats match — then scores **how far** you had to bend time.

## What we extracted

- **Why not plain distance:** finance phases **lag and stretch**.
- **Constraints (e.g. Sakoe–Chiba):** limit crazy warps; **speed + sanity**.
- **Lower bounds (e.g. LB_Keogh):** cheap tests to **skip** full DTW safely.
- **Libraries:** **dtaidistance** for speed; **fastdtw** often **not** recommended in literature.
- **Practice:** **z-normalize**, use **constrained** DTW, validate **out-of-sample**.

## Topic nodes

- [[DTW]]
- [[Pearson correlation]]
- [[SAX symbolic approximation]]

## Related

- [[Research hub]]
- [[Survey forecasting backtesting]]
