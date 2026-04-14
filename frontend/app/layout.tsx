import type { Metadata } from "next";
import { Inter, Instrument_Serif } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";
import { Navbar } from "@/components/Navbar";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const instrumentSerif = Instrument_Serif({
  weight: "400",
  subsets: ["latin"],
  variable: "--font-instrument",
});

export const metadata: Metadata = {
  title: "Deep Thesis — Startup Investment Intelligence",
  description:
    "Institutional-grade deal intelligence at angel investor pricing. 1,000+ buy-side VC transactions, secondaries data, AI agents, and quantitative analysis tools — starting at $19.99/mo.",
  icons: {
    icon: "/favicon.svg",
  },
  metadataBase: new URL("https://deepthesis.org"),
  openGraph: {
    title: "Deep Thesis — Startup Investment Intelligence",
    description:
      "1,000+ buy-side VC transactions, secondaries data, Crunchbase, PitchBook, and AI agents — so you can make quantitative investment decisions without a $20K/yr data subscription.",
    url: "https://deepthesis.org",
    siteName: "Deep Thesis",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Deep Thesis — Startup Investment Intelligence",
    description:
      "1,000+ buy-side VC transactions, secondaries data, and AI agents. Starting at $19.99/mo.",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${inter.variable} ${instrumentSerif.variable} font-sans`}>
        <Providers>
          <Navbar />
          <main className="mx-auto max-w-6xl px-6 lg:px-8 py-12">
            {children}
          </main>
        </Providers>
      </body>
    </html>
  );
}
