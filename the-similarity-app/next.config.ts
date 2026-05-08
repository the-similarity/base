import type { NextConfig } from "next";

const legacyLabRedirects = [
  ["/workstation", "/scanner"],
  ["/cadence", "/labs/cadence"],
  ["/fractal", "/labs/fractal"],
  ["/narrative", "/labs/narrative"],
  ["/prudent", "/labs/prudent"],
  ["/prudent-demo", "/labs/prudent-demo"],
  ["/spatium", "/labs/spatium"],
  ["/finance", "/labs/finance"],
  ["/portfolio", "/labs/portfolio"],
  ["/search", "/labs/search"],
  ["/reports", "/labs/reports"],
  ["/workstation/lumen", "/labs/workstation-lumen"],
  ["/explore", "/labs/explore"],
  ["/strategy", "/labs/strategy"],
  ["/demo", "/labs/demo"],
  ["/case-study/spy-2026-2007", "/labs/case-study-spy-2026-2007"],
] as const;

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async redirects() {
    return legacyLabRedirects.map(([source, destination]) => ({
      source,
      destination,
      permanent: false,
    }));
  },
};

export default nextConfig;
