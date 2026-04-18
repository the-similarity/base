import type { Metadata } from "next";
import "./globals.css";
import { ErrorBoundary } from "../components/error-boundary";

export const metadata: Metadata = {
  title: "The Similarity",
  description: "Research-grade time series pattern matching workstation",
};

/**
 * Root layout — provides the HTML shell with Google Fonts preconnect
 * for Newsreader, Inter, and JetBrains Mono. The old Nav component is
 * removed because the new workstation app shell handles its own navigation
 * inline (6-verb nav bar inside page.tsx).
 *
 * Theme initialization script runs before paint to prevent FOUC: reads
 * ts-theme from localStorage and sets data-theme + background color on
 * the <html> element synchronously.
 */
export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,400&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
        {/* Inline theme initialization to prevent flash of wrong theme */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem('ts-theme')||'light';document.documentElement.setAttribute('data-theme',t);document.documentElement.style.background=t==='dark'?'#0e0d0b':'#faf9f6';}catch(e){}})();`,
          }}
        />
      </head>
      <body>
        <ErrorBoundary>
          {children}
        </ErrorBoundary>
      </body>
    </html>
  );
}
