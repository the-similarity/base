/**
 * Lumen workstation — number/format helpers.
 *
 * Originally this module also held a large block of personal-finance
 * demo data (accounts, merchants, transactions, budgets, goals, etc.)
 * because the Lumen page was bootstrapped from a personal-finance
 * design bundle. After the rework the page wraps OUR product (analog
 * retrieval, finance runs, reviews, etc.) so the synthetic data is
 * gone and only the small currency/percent formatting helpers remain.
 *
 * Why we keep these here (instead of inlining in screens):
 *   - Screens render dollar/percent values for run summaries and KPIs.
 *   - Currency formatting must stay consistent across screens (commas,
 *     cents, signed prefix), and the safest way to enforce that is one
 *     module-level helper everyone calls.
 *   - These functions are pure, allocation-light, and don't depend on
 *     any React or DOM state — so they're cheap to import everywhere.
 *
 * Sign convention:
 *   - usd() and usdShort() use ASCII "-" (U+002D) so the minus sign
 *     pairs cleanly with `$` glyphs inside tabular-number tables.
 *   - pct() uses Unicode "−" (U+2212) so signed percentages line up
 *     to the typographic em-width that tabular-num fonts assume.
 */

/**
 * Currency / percent formatters used across Lumen screens.
 *
 * Immutability: this object is treated as a constant. Do NOT mutate
 * any of the methods — they are read concurrently from many screens
 * and any in-place change would silently affect every renderer.
 */
export const FMT = {
  /**
   * Format a number as USD currency.
   *
   * @param n      The numeric value (can be negative).
   * @param opts.sign  When true and n>0, prefix with "+" so deltas
   *                   render with explicit polarity. Default false.
   * @param opts.cents When true, render two decimal places. When
   *                   false, render zero decimals — used for whole-
   *                   dollar amounts in tighter table rows. Default true.
   */
  usd: (n: number, opts: { sign?: boolean; cents?: boolean } = {}): string => {
    const { sign = false, cents = true } = opts;
    const sgn = n < 0 ? "-" : sign && n > 0 ? "+" : "";
    const abs = Math.abs(n);
    return (
      sgn +
      "$" +
      abs.toLocaleString("en-US", {
        minimumFractionDigits: cents ? 2 : 0,
        maximumFractionDigits: cents ? 2 : 0,
      })
    );
  },

  /**
   * Format a number as a short-form currency string ($1.2k, $3.45M).
   * Used in KPI tiles where horizontal space is at a premium.
   */
  usdShort: (n: number): string => {
    const abs = Math.abs(n);
    const sgn = n < 0 ? "-" : "";
    if (abs >= 1e6) return sgn + "$" + (abs / 1e6).toFixed(2) + "M";
    if (abs >= 1e3) return sgn + "$" + (abs / 1e3).toFixed(1) + "k";
    return sgn + "$" + abs.toFixed(0);
  },

  /**
   * Format a percentage with optional explicit sign. Uses Unicode minus
   * (U+2212) so signed percentages line up to tabular-num glyph widths.
   */
  pct: (n: number, opts: { sign?: boolean } = {}): string => {
    const { sign = false } = opts;
    const sgn = n < 0 ? "−" : sign && n > 0 ? "+" : "";
    return sgn + Math.abs(n).toFixed(2) + "%";
  },
};
