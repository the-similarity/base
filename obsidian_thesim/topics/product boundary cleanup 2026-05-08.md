# Product boundary cleanup — 2026-05-08

Decision: `the-similarity-app/` is now treated as the sellable [[Similarity analysis]] setup scanner app first, not as the marketing landing page or a catch-all lab deploy.

- `/` redirects to `/scanner`, so localhost product development opens the scanner surface by default.
- `/scanner` is the canonical scanner route and currently reuses `the-similarity-app/app/workstation/page.tsx` until the larger `apps/scanner-web/` move happens.
- Legacy concept surfaces (`cadence`, `fractal`, `narrative`, `prudent`, `spatium`, `finance`, `explore`, `strategy`, demos/case studies) are catalogued under `/labs/*` via `the-similarity-app/lib/product-boundary.ts` and `the-similarity-app/app/labs/page.tsx`.
- Marketing copy belongs in the separate landing deploy target (`the-similarity-landing/` or future `apps/landing/`), not in the scanner app root.

Why: setup scanner sale work should not be blocked by unrelated lab pages or old product concepts. The current PR creates routing and test boundaries without attempting the large physical monorepo move in one step.

Next cleanup steps:

1. Physically move scanner UI to `apps/scanner-web/` and landing to `apps/landing/` when the repo can tolerate a broad move.
2. Split CI into scanner-web, landing, labs, scanner-api, core, platform, and data gates.
3. Promote a lab back to product only by first changing the boundary manifest and adding product ownership/test coverage.
