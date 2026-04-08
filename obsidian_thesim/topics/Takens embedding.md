# Takens embedding

**Problem:** you only observe **one line** (price), but the **system** might be higher-dimensional.

**Takens’ idea:** stack **delayed copies** of the line — \(x_t, x_{t-\tau}, x_{t-2\tau}, \ldots\) — to **reconstruct an attractor** (shape of dynamical behavior) under mild conditions.

## Why we use it

Feeds **[[Koopman operator|Koopman]]**, **[[TDA persistence|TDA]]**, and other **geometry-of-dynamics** tools from plain price series.

## Related

- [[Survey Koopman]]
- [[Survey TDA EMD wavelets SAX]]
