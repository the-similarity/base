# DTW

**Dynamic Time Warping** measures how alike two time series are when you **bend time** — allowing stretches and compressions so that **peaks can line up with peaks** even if one pattern unfolds faster.

## Why traders care

Market phases repeat **out of sync**: similar story, different calendar speed. DTW is built for that in a way plain “point-by-point” distance is not.

## Tradeoffs

- **Strength:** phase flexibility, keeps shape information.
- **Cost:** heavier than correlation; production systems use **constraints** and **lower bounds** (see [[Survey DTW]]).

## In our stack

Used as a **core similarity lens** after fast screens. See [[Nine-method pipeline]], [[Engine map]].

## Related

- [[Pearson correlation]]
- [[Survey DTW]]
- [[SAX symbolic approximation]] — sometimes used *before* DTW to prune candidates
