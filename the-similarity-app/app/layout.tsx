import type { Metadata } from "next";
import "./globals.css";

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
      <body>{children}</body>
    </html>
  );
}
