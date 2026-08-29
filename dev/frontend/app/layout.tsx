import type { Metadata } from "next";
import { Caveat } from "next/font/google";

import "./globals.css";

const handwriting = Caveat({
  display: "swap",
  subsets: ["latin"],
  variable: "--font-handwriting",
  weight: "variable",
});

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
    <html className={handwriting.variable} lang="en">
      <body>{children}</body>
    </html>
  );
}
