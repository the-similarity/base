/**
 * Lumen Finance — demo data + currency/percent format helpers.
 *
 * This module holds ALL synthetic personal-finance data used by the Lumen
 * workstation page (`/workstation/lumen`). It is intentionally a port of the
 * design-bundle `data.jsx` with TypeScript types added; numbers, account
 * names, and merchants are deliberately preserved verbatim so the screens
 * render the same scenario the user approved during design review.
 *
 * Data immutability: every export below is a frozen-by-convention literal.
 * Screens MUST treat the arrays as read-only. If you need a mutated copy,
 * spread/clone first — mutating in place will reflect across every screen
 * because the same module object is shared at runtime.
 *
 * Date anchor: TX entries are computed relative to a fixed "today" of
 * 2026-04-27 to match the design's screenshots. The dashboard heatmap and
 * upcoming list assume this anchor.
 */

// =====================================================================
// Format helpers — usd / usdShort / pct
// =====================================================================
//
// FMT.usd(n, { sign?: boolean, cents?: boolean }) -> "$1,234.56" / "+$12"
// FMT.usdShort(n) -> "$1.2k" / "$3.45M"
// FMT.pct(n, { sign?: boolean }) -> "−4.20%" / "+2.10%"
//
// The minus character used by FMT.pct is the Unicode "−" (U+2212) on purpose
// so signed percentages line up with the typographic em-width in tabular nums.
// usd() uses ASCII "-" because it pairs with currency glyphs in tables.
export const FMT = {
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
  usdShort: (n: number): string => {
    const abs = Math.abs(n);
    const sgn = n < 0 ? "-" : "";
    if (abs >= 1e6) return sgn + "$" + (abs / 1e6).toFixed(2) + "M";
    if (abs >= 1e3) return sgn + "$" + (abs / 1e3).toFixed(1) + "k";
    return sgn + "$" + abs.toFixed(0);
  },
  pct: (n: number, opts: { sign?: boolean } = {}): string => {
    const { sign = false } = opts;
    const sgn = n < 0 ? "−" : sign && n > 0 ? "+" : "";
    return sgn + Math.abs(n).toFixed(2) + "%";
  },
};

// =====================================================================
// Type definitions — used by both data + screens
// =====================================================================

export type AccountKind =
  | "Checking"
  | "Savings"
  | "Credit Card"
  | "Investment"
  | "Retirement"
  | "Loan";

export interface Account {
  id: string;
  name: string;
  bank: string;
  last4: string;
  kind: AccountKind;
  balance: number;
  color: string;
  logo: string;
  // Optional — only some account kinds carry these.
  apy?: number;
  limit?: number;
  due?: string;
}

export interface Category {
  label: string;
  color: string;
  icon: string;
}

export interface Merchant {
  color: string;
  mark: string;
  cat: string;
}

export interface Transaction {
  id: string;
  date: Date;
  merchant: string;
  amount: number; // negative = outflow, positive = inflow
  account: string; // foreign key into ACCOUNTS[].id
  note: string;
  category: string;
  cleared: boolean;
}

export interface Budget {
  cat: string;
  limit: number;
  spent: number;
}

export interface Goal {
  id: string;
  name: string;
  target: number;
  current: number;
  color: string;
  icon: string;
  eta: string;
}

export interface Holding {
  ticker: string;
  name: string;
  shares: number;
  price: number;
  cost: number;
  color: string;
}

export interface Subscription {
  name: string;
  amount: number;
  freq: string;
  next: string;
  color: string;
  mark: string;
}

export interface CashflowMonth {
  m: string;
  in: number;
  out: number;
}

export interface NetWorthPoint {
  m: string;
  v: number;
}

// =====================================================================
// ACCOUNTS — 8 entries spanning checking/savings/credit/investment/loan
// =====================================================================

export const ACCOUNTS: Account[] = [
  { id: "a1", name: "Everyday Checking", bank: "Chase", last4: "4821", kind: "Checking", balance: 8420.55, color: "#1d6cb1", logo: "CH" },
  { id: "a2", name: "High-Yield Savings", bank: "Marcus", last4: "0192", kind: "Savings", balance: 32140.18, color: "#0a6b48", logo: "MR", apy: 4.4 },
  { id: "a3", name: "Sapphire Preferred", bank: "Chase", last4: "7732", kind: "Credit Card", balance: -2184.32, color: "#0d2a4d", logo: "CH", limit: 25000, due: "Jun 14" },
  { id: "a4", name: "Apple Card", bank: "Goldman Sachs", last4: "3300", kind: "Credit Card", balance: -412.84, color: "#111", logo: "", limit: 8000, due: "Jun 21" },
  { id: "a5", name: "Brokerage", bank: "Fidelity", last4: "2210", kind: "Investment", balance: 142308.92, color: "#3b8d40", logo: "FD" },
  { id: "a6", name: "Roth IRA", bank: "Vanguard", last4: "1148", kind: "Investment", balance: 48201.03, color: "#a4262c", logo: "VG" },
  { id: "a7", name: "401(k)", bank: "Fidelity NetBenefits", last4: "5567", kind: "Retirement", balance: 88420.0, color: "#3b8d40", logo: "FD" },
  { id: "a8", name: "Mortgage", bank: "Rocket", last4: "8821", kind: "Loan", balance: -284200.0, color: "#c2410c", logo: "RK" },
];

// =====================================================================
// CATEGORIES — keyed by short slug; each carries label, color, and an
// icon name resolvable via the Icon component.
// =====================================================================

export const CATEGORIES: Record<string, Category> = {
  groceries: { label: "Groceries", color: "#0a6b48", icon: "cart" },
  dining: { label: "Dining", color: "#b14a3a", icon: "coffee" },
  transport: { label: "Transport", color: "#2e5d8c", icon: "car" },
  shopping: { label: "Shopping", color: "#7d3aa9", icon: "cart" },
  housing: { label: "Housing", color: "#1a1a1a", icon: "house" },
  utilities: { label: "Utilities", color: "#b07c1d", icon: "zap" },
  entertain: { label: "Entertainment", color: "#c84a8e", icon: "play" },
  health: { label: "Health", color: "#0a8c7a", icon: "leaf" },
  fitness: { label: "Fitness", color: "#3d6a3d", icon: "gym" },
  travel: { label: "Travel", color: "#5c4a8c", icon: "plane" },
  subscriptions: { label: "Subscriptions", color: "#4a4a48", icon: "repeat" },
  income: { label: "Income", color: "#0a6b48", icon: "arrowDown" },
  transfer: { label: "Transfer", color: "#7a7a75", icon: "flow" },
  fees: { label: "Fees", color: "#7a2f24", icon: "receipt" },
  taxes: { label: "Taxes", color: "#3d3d3a", icon: "receipt" },
};

// =====================================================================
// MERCHANTS — visual metadata for tx rows. Each name maps to a tile
// color, two-letter mark, and the default category that feeds tx.category.
// =====================================================================

export const MERCHANTS: Record<string, Merchant> = {
  "Whole Foods": { color: "#0a6b48", mark: "WF", cat: "groceries" },
  "Trader Joe's": { color: "#a4262c", mark: "TJ", cat: "groceries" },
  "Blue Bottle": { color: "#1d4d8c", mark: "BB", cat: "dining" },
  Sweetgreen: { color: "#3d6a3d", mark: "SG", cat: "dining" },
  Tartine: { color: "#7a3a1a", mark: "TR", cat: "dining" },
  Chipotle: { color: "#a4262c", mark: "CP", cat: "dining" },
  Uber: { color: "#0e0e0e", mark: "U", cat: "transport" },
  Lyft: { color: "#c84a8e", mark: "L", cat: "transport" },
  Shell: { color: "#b07c1d", mark: "SH", cat: "transport" },
  Amazon: { color: "#1a1a1a", mark: "A", cat: "shopping" },
  Apple: { color: "#111", mark: "", cat: "shopping" },
  Target: { color: "#a4262c", mark: "T", cat: "shopping" },
  "Pacific Gas & Electric": { color: "#1d6cb1", mark: "PG", cat: "utilities" },
  Comcast: { color: "#1a1a1a", mark: "C", cat: "utilities" },
  "T-Mobile": { color: "#c41067", mark: "TM", cat: "utilities" },
  Netflix: { color: "#a4262c", mark: "N", cat: "subscriptions" },
  Spotify: { color: "#0a6b48", mark: "S", cat: "subscriptions" },
  Notion: { color: "#1a1a1a", mark: "N", cat: "subscriptions" },
  Figma: { color: "#7d3aa9", mark: "F", cat: "subscriptions" },
  iCloud: { color: "#2e5d8c", mark: "iC", cat: "subscriptions" },
  Equinox: { color: "#1a1a1a", mark: "E", cat: "fitness" },
  "United Airlines": { color: "#0d2a4d", mark: "UA", cat: "travel" },
  Airbnb: { color: "#c41067", mark: "A", cat: "travel" },
  "Stripe Payroll": { color: "#5c4ad6", mark: "SP", cat: "income" },
  "Rocket Mortgage": { color: "#c2410c", mark: "RM", cat: "housing" },
  IRS: { color: "#3d3d3a", mark: "IR", cat: "taxes" },
  "Transfer to Marcus": { color: "#7a7a75", mark: "↻", cat: "transfer" },
};

// =====================================================================
// TX — 67 transactions across the last 60 days, anchored at 2026-04-27.
//
// Each entry was authored as a tuple [daysAgo, merchant, amount, account, note?]
// then expanded into a Transaction. The expansion preserves the design's
// "cleared = days > 0" rule (today's items still pending).
// =====================================================================

type TxSeed = [number, string, number, string, string?];

const TX_SEED: TxSeed[] = [
  [0, "Blue Bottle", -6.75, "a4", "Latte"],
  [0, "Whole Foods", -84.2, "a3", "Weekly grocery run"],
  [0, "Uber", -14.32, "a4"],
  [1, "Sweetgreen", -16.4, "a4"],
  [1, "Amazon", -129.99, "a3", "Sony WH-1000XM5"],
  [1, "Notion", -10.0, "a3", "Plus plan"],
  [2, "Shell", -52.1, "a3"],
  [2, "Spotify", -11.99, "a3"],
  [2, "Tartine", -28.4, "a4"],
  [3, "Trader Joe's", -42.18, "a1"],
  [3, "T-Mobile", -85.0, "a3", "Family plan"],
  [4, "Equinox", -245.0, "a3", "Monthly membership"],
  [4, "Lyft", -22.4, "a4"],
  [5, "Apple", -9.99, "a4", "iCloud 200GB"],
  [5, "Stripe Payroll", 6428.1, "a1", "Bi-weekly"],
  [5, "Rocket Mortgage", -2840.0, "a1", "June payment"],
  [6, "Pacific Gas & Electric", -142.38, "a1"],
  [6, "Netflix", -22.99, "a3", "Premium"],
  [7, "Whole Foods", -68.1, "a3"],
  [7, "Chipotle", -14.85, "a4"],
  [8, "Figma", -15.0, "a3"],
  [8, "Uber", -19.2, "a4"],
  [9, "Comcast", -89.0, "a1", "Internet"],
  [9, "Amazon", -34.5, "a3"],
  [10, "Transfer to Marcus", -2000.0, "a1", "Auto-save"],
  [10, "Trader Joe's", -38.8, "a3"],
  [11, "United Airlines", -412.3, "a3", "SFO → JFK"],
  [11, "Airbnb", -680.0, "a3", "Brooklyn 4 nights"],
  [12, "Sweetgreen", -18.2, "a4"],
  [13, "Target", -76.45, "a3"],
  [14, "Stripe Payroll", 6428.1, "a1"],
  [14, "Blue Bottle", -7.25, "a4"],
  [15, "Whole Foods", -91.8, "a3"],
  [16, "IRS", -1200.0, "a1", "Q2 estimated"],
  [17, "Tartine", -32.1, "a4"],
  [18, "Shell", -48.2, "a3"],
  [19, "Amazon", -22.0, "a3"],
  [20, "Lyft", -16.8, "a4"],
  [21, "Notion", -10.0, "a3"],
  [22, "Spotify", -11.99, "a3"],
  [23, "Apple", -9.99, "a4"],
  [24, "Whole Foods", -72.4, "a3"],
  [25, "Sweetgreen", -15.4, "a4"],
  [26, "Equinox", -245.0, "a3"],
  [27, "Netflix", -22.99, "a3"],
  [28, "Stripe Payroll", 6428.1, "a1"],
  [28, "Rocket Mortgage", -2840.0, "a1"],
  [29, "Comcast", -89.0, "a1"],
  [30, "Pacific Gas & Electric", -128.1, "a1"],
  [31, "Trader Joe's", -52.3, "a3"],
  [32, "Uber", -22.4, "a4"],
  [33, "Figma", -15.0, "a3"],
  [34, "Chipotle", -16.2, "a4"],
  [35, "Amazon", -88.4, "a3"],
  [36, "Tartine", -29.8, "a4"],
  [38, "Blue Bottle", -6.75, "a4"],
  [40, "Target", -124.5, "a3"],
  [42, "Stripe Payroll", 6428.1, "a1"],
  [42, "Whole Foods", -88.2, "a3"],
  [44, "Shell", -56.8, "a3"],
  [46, "Sweetgreen", -17.4, "a4"],
  [48, "United Airlines", -312.0, "a3", "SFO → SEA"],
  [50, "Lyft", -19.4, "a4"],
  [52, "Notion", -10.0, "a3"],
  [54, "Spotify", -11.99, "a3"],
  [56, "Apple", -9.99, "a4"],
  [56, "Stripe Payroll", 6428.1, "a1"],
  [58, "Equinox", -245.0, "a3"],
  [60, "Netflix", -22.99, "a3"],
];

// Anchor "today" at 2026-04-27 so the heatmap and "Net" labels match the
// design's expected layout regardless of the real wall-clock date when this
// file is imported. This is module-load constant — never mutate.
const TX_TODAY = new Date("2026-04-27T00:00:00Z");

export const TX: Transaction[] = TX_SEED.map(([d, m, amt, acct, note], i) => {
  const date = new Date(TX_TODAY);
  date.setDate(date.getDate() - d);
  return {
    id: "t" + i,
    date,
    merchant: m,
    amount: amt,
    account: acct,
    note: note || "",
    category: MERCHANTS[m]?.cat || "shopping",
    cleared: d > 0,
  };
});

// =====================================================================
// BUDGETS / GOALS / HOLDINGS / SUBSCRIPTIONS / CASHFLOW / NETWORTH
// =====================================================================

export const BUDGETS: Budget[] = [
  { cat: "groceries", limit: 600, spent: 487.18 },
  { cat: "dining", limit: 350, spent: 412.85 },
  { cat: "transport", limit: 300, spent: 188.62 },
  { cat: "shopping", limit: 400, spent: 364.94 },
  { cat: "utilities", limit: 350, spent: 360.38 },
  { cat: "entertain", limit: 150, spent: 84.97 },
  { cat: "fitness", limit: 250, spent: 245.0 },
  { cat: "travel", limit: 800, spent: 1404.3 },
  { cat: "subscriptions", limit: 120, spent: 84.96 },
];

export const GOALS: Goal[] = [
  { id: "g1", name: "Emergency fund", target: 30000, current: 24800, color: "#0a6b48", icon: "leaf", eta: "Aug 2026" },
  { id: "g2", name: "Japan trip", target: 6500, current: 4120, color: "#a4262c", icon: "plane", eta: "Oct 2026" },
  { id: "g3", name: "New laptop", target: 3500, current: 1850, color: "#1a1a1a", icon: "zap", eta: "Sep 2026" },
  { id: "g4", name: "House down payment", target: 120000, current: 41200, color: "#3d3d3a", icon: "house", eta: "Q4 2028" },
];

export const HOLDINGS: Holding[] = [
  { ticker: "VTI", name: "Vanguard Total Market", shares: 184.2, price: 268.42, cost: 198.1, color: "#a4262c" },
  { ticker: "VXUS", name: "Vanguard Intl. Stock", shares: 220.0, price: 62.18, cost: 56.4, color: "#a4262c" },
  { ticker: "AAPL", name: "Apple Inc.", shares: 45.0, price: 218.74, cost: 142.3, color: "#111" },
  { ticker: "MSFT", name: "Microsoft", shares: 28.0, price: 432.16, cost: 312.4, color: "#1d6cb1" },
  { ticker: "NVDA", name: "NVIDIA", shares: 18.0, price: 1182.4, cost: 462.2, color: "#3b8d40" },
  { ticker: "BND", name: "Vanguard Total Bond", shares: 240.0, price: 72.1, cost: 74.4, color: "#7a7a75" },
  { ticker: "VNQ", name: "Vanguard Real Estate", shares: 60.0, price: 88.1, cost: 92.3, color: "#5c4a8c" },
];

export const SUBSCRIPTIONS: Subscription[] = [
  { name: "Netflix", amount: 22.99, freq: "Monthly", next: "Jun 6", color: "#a4262c", mark: "N" },
  { name: "Spotify", amount: 11.99, freq: "Monthly", next: "Jun 2", color: "#0a6b48", mark: "S" },
  { name: "Notion", amount: 10.0, freq: "Monthly", next: "Jun 10", color: "#1a1a1a", mark: "N" },
  { name: "Figma", amount: 15.0, freq: "Monthly", next: "Jun 8", color: "#7d3aa9", mark: "F" },
  { name: "iCloud+", amount: 9.99, freq: "Monthly", next: "Jun 5", color: "#2e5d8c", mark: "iC" },
  { name: "Equinox", amount: 245.0, freq: "Monthly", next: "Jun 4", color: "#1a1a1a", mark: "E" },
  { name: "NYT", amount: 17.0, freq: "Monthly", next: "Jun 12", color: "#1a1a1a", mark: "NY" },
  { name: "AWS", amount: 42.3, freq: "Monthly", next: "Jun 1", color: "#b07c1d", mark: "AW" },
];

export const CASHFLOW: CashflowMonth[] = [
  { m: "May 25", in: 11200, out: 7820 },
  { m: "Jun 25", in: 12856, out: 8920 },
  { m: "Jul 25", in: 12856, out: 9410 },
  { m: "Aug 25", in: 11200, out: 7180 },
  { m: "Sep 25", in: 14320, out: 9680 },
  { m: "Oct 25", in: 12856, out: 8240 },
  { m: "Nov 25", in: 12856, out: 9920 },
  { m: "Dec 25", in: 16400, out: 11800 },
  { m: "Jan 26", in: 12856, out: 8420 },
  { m: "Feb 26", in: 12856, out: 7980 },
  { m: "Mar 26", in: 14200, out: 9180 },
  { m: "Apr 26", in: 12856, out: 8640 },
];

export const NETWORTH: NetWorthPoint[] = [
  { m: "May 25", v: 198400 },
  { m: "Jun 25", v: 202100 },
  { m: "Jul 25", v: 199200 },
  { m: "Aug 25", v: 208400 },
  { m: "Sep 25", v: 215800 },
  { m: "Oct 25", v: 211400 },
  { m: "Nov 25", v: 222900 },
  { m: "Dec 25", v: 236200 },
  { m: "Jan 26", v: 232100 },
  { m: "Feb 26", v: 244800 },
  { m: "Mar 26", v: 251400 },
  { m: "Apr 26", v: 263894 },
];
