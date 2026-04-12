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
  description: "AI scoring, expert due diligence, and community reviews for startup investments.",
  icons: {
    icon: "/favicon.svg",
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
