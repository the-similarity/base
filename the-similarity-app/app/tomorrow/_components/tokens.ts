export const TOMORROW_TOKENS = {
  storageKeys: {
    entries: "prudent:entries:v1",
  },
  routes: [
    { id: "today", label: "Today", href: "/tomorrow" },
    { id: "thread", label: "Thread", href: "/tomorrow/thread" },
    { id: "rhymes", label: "Similar days", href: "/tomorrow/rhymes" },
    { id: "tags", label: "Themes", href: "/tomorrow/tags" },
    { id: "patterns", label: "Repeats", href: "/tomorrow/patterns" },
    { id: "experiment", label: "Daily read", href: "/tomorrow/experiment" },
    { id: "subscribe", label: "Pro", href: "/tomorrow/subscribe" },
    { id: "entries", label: "Entries", href: "/tomorrow/entries" },
    { id: "engine", label: "How it works", href: "/tomorrow/engine" },
  ],
} as const;

export type TomorrowRouteId = (typeof TOMORROW_TOKENS.routes)[number]["id"];
