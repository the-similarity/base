import type { Metadata } from "next";
import { Nav } from "../components/nav";
import "./globals.css";
import { ErrorBoundary } from "../components/error-boundary";

export const metadata: Metadata = {
  title: "The Similarity Dashboard",
  description: "Research-grade time series pattern matching dashboard",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <Nav />
        <ErrorBoundary>
          {children}
        </ErrorBoundary>
      </body>
    </html>
  );
}
