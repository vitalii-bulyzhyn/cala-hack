import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Travel Journal",
  description: "A hand-drawn day plan for a city you want to discover.",
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
