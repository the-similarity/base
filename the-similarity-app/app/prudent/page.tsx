import type { Metadata } from "next";
import Dashboard from "./dashboard";

export const metadata: Metadata = {
  title: "Prudent — The Similarity",
  description:
    "Natural Language → Time Series. Describe your day in words; the engine compiles it into a chart and logs it to your thread.",
};

export default function PrudentPage() {
  return <Dashboard />;
}
