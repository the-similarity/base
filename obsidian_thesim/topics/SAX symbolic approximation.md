# SAX symbolic approximation

**SAX** turns a noisy numeric window into a **short string of symbols** (like an alphabet summary). Similar windows tend to get **similar strings**.

## Why we use it

It is **fast** — good for **Tier 1** screening. A clever distance on symbols (**MINDIST**) **lower-bounds** true distance, so we can **discard** bad candidates without accidentally throwing away true matches.

## Related

- [[Matrix Profile]]
- [[Survey TDA EMD wavelets SAX]]
- [[How the matcher works (simple)]]
