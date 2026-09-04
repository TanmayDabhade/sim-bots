import type { Metadata } from "next";
import "@fontsource-variable/instrument-sans";
import "@fontsource/ibm-plex-mono/500.css";
import "./globals.css";


export const metadata: Metadata = {
  title: "AI Market Arena",
  description: "Four open-model families compete with simulated stock portfolios.",
};


export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

