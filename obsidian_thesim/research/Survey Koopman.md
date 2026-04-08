# Survey Koopman

**Repo source:** `research/methods/03-koopman-operator-dmd.md`  
**Full write-up in vault:** [[03-koopman-operator-dmd]]

## Friendly summary

Even if the world is **nonlinear**, there is often a **lifting** where evolution looks **linear** — like switching from messy circles to clean matrix math. **Eigenvalues** become a **signature** of the engine humming underneath.

## What we extracted

- **Koopman / EDMD:** learn linear models in **feature space** (polynomials, delays, RBFs…).
- **Spectra compare systems:** similar **eigenvalues** ⇒ similar dynamics (with care).
- **Takens delays:** rebuild attractors from **one** observed series.
- **Tooling:** PyKoopman, PyDMD, datafold ecosystem.
- **Matching:** assignment problems when pairing eigenvalues.

## Topic nodes

- [[Koopman operator]]
- [[Takens embedding]]

## Related

- [[Research hub]]
- [[Nine-method pipeline]]
