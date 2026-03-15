import type { Metadata } from "next";
import "./globals.css";
import { ErrorBoundary } from "../components/error-boundary";

export const metadata: Metadata = {
  title: "The Similarity Terminal",
  description: "Bloomberg-style time series pattern matching terminal",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" data-theme="dark">
      <body>
        <ErrorBoundary>{children}</ErrorBoundary>
      </body>
    </html>
  );
}
