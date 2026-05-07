"""Curated feature presets for the finance pillar.

Presets are *declarative* feature packs — a list of variable specs with
ticker hints and citations. They do **not** fetch data. Callers compose them
with whatever data source they already use (FRED, Bloomberg, yfinance, the
project's own cached parquet) and feed the resulting frame into the engine.

This separation keeps the presets reusable across data backends and lets
``the_similarity`` stay agnostic about credentials.

Adding a preset
---------------
1. Define a tuple of :class:`MacroVariable` objects.
2. Wrap it in a :class:`FeaturePreset` with ``name``, ``description``,
   ``citation`` (if borrowed from a paper), and the variable tuple.
3. Add the preset to :data:`PRESETS` so it shows up in
   :func:`list_presets`.
4. Update the corresponding Obsidian research note under
   ``obsidian_thesim/research/full-text/notes/`` if the preset comes from
   a published source.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MacroVariable:
    """One declarative macro feature spec.

    Attributes:
        code: Short uppercase identifier used inside the engine
            (e.g. ``"FED"``, ``"TERM"``). Stable across backends.
        description: Human-readable label.
        fred_series: Free-text hint pointing to the FRED series id when one
            exists. Set to ``None`` when the variable is not on FRED (e.g.
            constructed spreads, FX rates with multiple plausible sources).
        bloomberg_ticker: Free-text Bloomberg ticker hint. Same nullability
            convention as ``fred_series``. Most academic papers cite the
            Bloomberg side; we keep both so users can wire to either backend.
        transform: Free-text description of the transform applied before
            the variable is fed to the engine. Examples: ``"daily change"``,
            ``"log return"``, ``"level"``. Mirrors how the source paper
            standardises inputs so reviewers can reproduce results without
            re-reading the implementation.
    """

    code: str
    description: str
    fred_series: str | None
    bloomberg_ticker: str | None
    transform: str


@dataclass(frozen=True)
class FeaturePreset:
    """A named bundle of :class:`MacroVariable` definitions plus citation.

    Presets are immutable so they can be safely shared across threads /
    processes. The ``variables`` field is a tuple rather than a list to
    preserve immutability under :func:`dataclasses.dataclass` semantics.

    The ``window_size`` is *advisory* — it records the window length the
    source paper used, so reproductions can match it. The engine itself
    does not constrain callers to this value.
    """

    name: str
    description: str
    citation: str
    variables: tuple[MacroVariable, ...]
    window_size: int

    def codes(self) -> tuple[str, ...]:
        """Return the variable codes in declared order.

        Used by callers to align dataframe columns with the preset's
        canonical ordering. Order matters when correlation distance is
        computed across a flattened (window_size, n_vars) matrix because
        feature ordering changes the flattened vector.
        """
        return tuple(v.code for v in self.variables)


# -------------------------------------------------------------------------
# Correia (2015) "primary case" — six US macro variables that the paper
# found significant. The "alternative case" (which substituted DEF and
# realised volatility for MRP and FX) was abandoned by the paper itself
# for lack of explanatory power, so we do not mirror it here.
#
# All variables are taken at the daily frequency and converted to daily
# changes prior to forming the 20-day regime matrix. The ``transform``
# field documents this so reviewers do not have to re-derive it.
# -------------------------------------------------------------------------

_CORREIA_2015_VARS: tuple[MacroVariable, ...] = (
    MacroVariable(
        code="FED",
        description="3-month constant maturity Treasury yield",
        fred_series="DGS3MO",
        bloomberg_ticker="USGG3M Index",
        transform="daily change",
    ),
    MacroVariable(
        code="STY",
        description="2-year constant maturity Treasury yield",
        fred_series="DGS2",
        bloomberg_ticker="USGG2YR Index",
        transform="daily change",
    ),
    MacroVariable(
        code="LTY",
        description="10-year constant maturity Treasury yield",
        fred_series="DGS10",
        bloomberg_ticker="USGG10YR Index",
        transform="daily change",
    ),
    MacroVariable(
        code="TERM",
        description="10Y - 3M term spread (yield curve slope)",
        # Constructed from DGS10 - DGS3MO; T10Y3M is the FRED-published
        # spread but uses end-of-day values that differ trivially from the
        # constructed version. Either is acceptable for reproductions.
        fred_series="T10Y3M",
        bloomberg_ticker=None,
        transform="daily change of constructed spread",
    ),
    MacroVariable(
        code="MRP",
        description="S&P 500 daily return (market risk premium proxy)",
        fred_series="SP500",
        bloomberg_ticker="SPX Index",
        transform="log return",
    ),
    MacroVariable(
        code="FX",
        description="EUR/USD exchange rate (cross-currency macro)",
        fred_series="DEXUSEU",
        bloomberg_ticker="EURUSD Curncy",
        transform="log return",
    ),
)


MACRO_US_CORREIA_2015 = FeaturePreset(
    name="macro_us_correia_2015",
    description=(
        "US macro regime feature pack from Correia (2015) 'An Analog Model "
        "for Global Macro Investing'. Six daily-frequency variables that the "
        "paper found load on growth, inflation, monetary policy, and "
        "cross-currency macro state. Suitable for asset-allocation analog "
        "matching (Sharpe 1.27 in the paper's Dynamic Equity/Bond test, "
        "1991-2014). NOT suitable for style or sector rotation - the paper "
        "shows analog matching with these features fails on fine-grained "
        "equity decisions (style test had MaxDD -73.5%)."
    ),
    citation=(
        "Correia, G. G. (2015). An Analog Model for Global Macro Investing. "
        "Directed Research Project, Nova School of Business and Economics."
    ),
    variables=_CORREIA_2015_VARS,
    # The paper standardises a 20-trading-day (~1 month) window and computes
    # the Pearson correlation between flattened (20, 6) regime matrices.
    window_size=20,
)


# Registry of all available presets. Keep keys lowercased and matching the
# preset's ``name`` field so list-and-fetch round-trips cleanly.
PRESETS: dict[str, FeaturePreset] = {
    MACRO_US_CORREIA_2015.name: MACRO_US_CORREIA_2015,
}


def list_presets() -> list[str]:
    """Return the registered preset names sorted alphabetically.

    Stable ordering matters for snapshot tests and CLI output that lists
    available presets to users.
    """
    return sorted(PRESETS.keys())


def get_preset(name: str) -> FeaturePreset:
    """Look up a preset by name.

    Args:
        name: Preset name (e.g. ``"macro_us_correia_2015"``).

    Raises:
        KeyError: If the name is not registered. The error message lists
            the available names so callers can self-correct without
            re-reading the source.
    """
    try:
        return PRESETS[name]
    except KeyError as exc:
        available = ", ".join(list_presets())
        raise KeyError(f"unknown preset '{name}'. available: {available}") from exc


__all__ = [
    "FeaturePreset",
    "MACRO_US_CORREIA_2015",
    "MacroVariable",
    "PRESETS",
    "get_preset",
    "list_presets",
]
