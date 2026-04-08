# Why nine lenses

One number can lie. **Shape** might match while **dynamics** don’t, or **scaling** matches while **future predictability** doesn’t.

Each **method** is a different question:

**Fast screens (not counted in the nine scored lenses):** [[SAX symbolic approximation]], [[Matrix Profile]] — they **narrow** history before expensive work.

**Nine scored lenses (composite score):**

| Lens | Plain question |
|------|----------------|
| [[DTW]] | Do curves match if we allow time stretching? |
| [[Pearson correlation]] | After alignment, do they move together linearly? |
| [[Bempedelis power-law match|Bempedelis]] | Same **power-law scaling** story (and is it a clean fit)? |
| [[Wavelet leaders]] | Same **multifractal fingerprint** across time scales? |
| [[Koopman operator|Koopman]] | Same underlying **dynamical engine** (growth / oscillation modes)? |
| [[EMD and IMFs|EMD]] | Similar **trend + rhythm layers** when peeled apart? |
| [[TDA persistence|TDA]] | Same **loop / hole structure** in reconstructed space? |
| [[Transfer entropy]] | Did the match **actually carry information** about the future? |

(Some implementations split one family — e.g. Bempedelis — into two score components; think “same idea, two quality checks.”)

High agreement across **different dimensions** is stronger evidence than one metric shouting “close!”

## Related

- [[How the matcher works (simple)]]
- [[topics/Methods index]]
