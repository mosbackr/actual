"use client";

import Link from "next/link";
import { useSession } from "next-auth/react";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { BillingStatus } from "@/lib/types";
import { TIERS } from "@/lib/pricing";

const DATA_SOURCES = [
  {
    title: "Buy-Side Transaction Data",
    description:
      "1,000+ closed VC transactions with pricing, terms, and outcomes from actual buy-side deals.",
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 2v20M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6" />
      </svg>
    ),
  },
  {
    title: "VC Secondaries Market",
    description:
      "Real secondary market pricing and liquidity data on venture-backed companies — the layer most platforms ignore.",
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 3v18h18" />
        <path d="M7 16l4-8 4 5 5-9" />
      </svg>
    ),
  },
  {
    title: "Crunchbase + PitchBook",
    description:
      "Funding rounds, investors, team data, and company profiles aggregated and cross-referenced.",
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <ellipse cx="12" cy="5" rx="9" ry="3" />
        <path d="M3 5v14c0 1.66 4.03 3 9 3s9-1.34 9-3V5" />
        <path d="M3 12c0 1.66 4.03 3 9 3s9-1.34 9-3" />
      </svg>
    ),
  },
  {
    title: "AI Agent Network",
    description:
      "An army of specialized agents that continuously evaluate companies across 8 dimensions — market, team, traction, technology, competition, financials, and more.",
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <rect x="4" y="4" width="16" height="16" rx="2" />
        <path d="M9 9h6M9 13h6M9 17h4" />
      </svg>
    ),
  },
];

const TOOLS = [
  {
    number: "01",
    title: "Company Search & Discovery",
    description:
      "Browse 2,800+ venture-backed companies with structured profiles — founders, funding history, investors, tech stack, competitors. Filter by stage, industry, state, AI score. Every profile backed by multi-source data.",
    cta: "Explore companies",
    href: "/startups",
  },
  {
    number: "02",
    title: "Startup Analysis",
    description:
      "Upload a pitch deck and documents. Eight AI agents independently evaluate the company across market, team, traction, technology, competition, GTM, financials, and problem/solution fit. Get a scored report with fundraising projections — your first analysis is free.",
    cta: "Try it free",
    href: "/analyze",
  },
  {
    number: "03",
    title: "VC Quant Agent",
    description:
      "Ask questions across our entire dataset. Draft investment memos. Run quantitative comparisons. Generate reports grounded in real transaction data, not vibes. The analyst you'd hire for $150K — available on demand.",
    cta: "Try it",
    href: "/insights",
  },
];

export default function LandingPage() {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;
  const [billing, setBilling] = useState<BillingStatus | null>(null);
  const [checkoutLoading, setCheckoutLoading] = useState<string | null>(null);

  const loadBilling = useCallback(async () => {
    if (!token) return;
    try {
      const data = await api.getBillingStatus(token);
      setBilling(data);
    } catch {
      // silent
    }
  }, [token]);

  useEffect(() => {
    loadBilling();
  }, [loadBilling]);

  const handleCheckout = async (tierKey: string) => {
    if (!token) return;
    setCheckoutLoading(tierKey);
    try {
      const { url } = await api.createCheckoutSession(token, tierKey);
      window.location.href = url;
    } catch (err: any) {
      alert(err.message || "Failed to start checkout");
      setCheckoutLoading(null);
    }
  };

  const handlePortal = async () => {
    if (!token) return;
    try {
      const { url } = await api.createPortalSession(token);
      window.location.href = url;
    } catch (err: any) {
      alert(err.message || "Failed to open billing portal");
    }
  };

  const subStatus = billing?.subscription_status || "none";
  const subTier = billing?.subscription_tier;

  return (
    <div className="-mx-6 lg:-mx-8 -mt-12">
      {/* Hero */}
      <section className="px-6 lg:px-8 pt-28 pb-20 text-center">
        <h1 className="font-serif text-5xl md:text-6xl lg:text-7xl text-text-primary max-w-4xl mx-auto leading-[1.1] tracking-tight">
          Institutional-grade deal intelligence.
          <br />
          <span className="text-accent">Angel investor price.</span>
        </h1>
        <p className="text-text-secondary text-lg md:text-xl mt-8 max-w-2xl mx-auto leading-relaxed">
          Deep Thesis aggregates data from 1,000+ buy-side VC transactions,
          secondaries markets, Crunchbase, PitchBook, and an army of AI agents
          — so you can make quantitative investment decisions without a $20K/yr
          data subscription.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mt-10">
          <Link
            href="/analyze"
            className="px-8 py-3.5 bg-accent text-white text-sm font-medium rounded hover:bg-accent-hover transition"
          >
            Analyze a Startup — Free
          </Link>
          <a
            href="#pricing"
            className="px-8 py-3.5 border border-border text-text-secondary text-sm font-medium rounded hover:border-text-tertiary hover:text-text-primary transition"
          >
            See Pricing
          </a>
        </div>

        {/* Stat bar */}
        <div className="mt-16 flex flex-col sm:flex-row items-center justify-center gap-6 sm:gap-12 py-5 border-y border-border">
          {[
            { value: "1,000+", label: "transactions tracked" },
            { value: "2,800+", label: "companies profiled" },
            { value: "8", label: "AI agents per analysis" },
          ].map((stat) => (
            <div key={stat.label} className="text-center">
              <span className="text-2xl font-serif text-text-primary tabular-nums">
                {stat.value}
              </span>
              <p className="text-xs text-text-tertiary mt-1">{stat.label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* The Problem */}
      <section className="px-6 lg:px-8 py-20 border-t border-border">
        <div className="max-w-5xl mx-auto">
          <h2 className="font-serif text-3xl md:text-4xl text-text-primary text-center mb-14">
            The math doesn&apos;t work.
          </h2>
          <div className="grid md:grid-cols-2 gap-12 md:gap-16">
            <div>
              <div className="space-y-4">
                {[
                  { label: "PitchBook", value: "~$20,000/yr" },
                  { label: "Crunchbase Pro", value: "~$5,000/yr" },
                  { label: "Your average check size", value: "$25K–$50K" },
                ].map((row) => (
                  <div key={row.label} className="flex items-center justify-between py-3 border-b border-border">
                    <span className="text-sm text-text-secondary">{row.label}</span>
                    <span className="text-sm font-medium text-text-primary tabular-nums">{row.value}</span>
                  </div>
                ))}
              </div>
              <p className="text-sm text-text-tertiary mt-6 italic">
                You shouldn&apos;t need to spend more on data than you deploy in a deal.
              </p>
            </div>
            <div className="flex items-center">
              <p className="text-lg text-text-secondary leading-relaxed">
                Deep Thesis was built for investors who write their own checks — angels, scouts, solo GPs, and emerging managers who need{" "}
                <span className="text-text-primary font-medium">real data</span>, not a Bloomberg terminal budget.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Data Sources */}
      <section className="px-6 lg:px-8 py-20 border-t border-border bg-surface">
        <div className="max-w-5xl mx-auto">
          <h2 className="font-serif text-3xl md:text-4xl text-text-primary text-center mb-14">
            Data you can&apos;t Google.
          </h2>
          <div className="grid md:grid-cols-2 gap-6">
            {DATA_SOURCES.map((source) => (
              <div key={source.title} className="rounded border border-border bg-background p-6 hover:border-text-tertiary transition">
                <div className="w-10 h-10 rounded bg-accent/10 flex items-center justify-center mb-4 text-accent">
                  {source.icon}
                </div>
                <h3 className="text-sm font-medium text-text-primary mb-2">{source.title}</h3>
                <p className="text-sm text-text-secondary leading-relaxed">{source.description}</p>
              </div>
            ))}
          </div>
          <p className="text-sm text-text-tertiary text-center mt-8">
            All of this feeds into every company profile, every analysis, and every report you generate.
          </p>
        </div>
      </section>

      {/* Three Core Tools */}
      <section className="px-6 lg:px-8 py-20 border-t border-border">
        <div className="max-w-4xl mx-auto">
          <h2 className="font-serif text-3xl md:text-4xl text-text-primary text-center mb-14">
            Search. Analyze. Reason.
          </h2>
          <div className="space-y-12">
            {TOOLS.map((tool) => (
              <div key={tool.number} className="flex gap-6 md:gap-8">
                <div className="shrink-0">
                  <span className="font-serif text-3xl text-accent/30">{tool.number}</span>
                </div>
                <div>
                  <h3 className="text-lg font-medium text-text-primary mb-2">{tool.title}</h3>
                  <p className="text-sm text-text-secondary leading-relaxed mb-3">{tool.description}</p>
                  <Link href={tool.href} className="text-sm text-accent hover:text-accent-hover transition">
                    {tool.cta} &rarr;
                  </Link>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="px-6 lg:px-8 py-20 border-t border-border bg-surface scroll-mt-16">
        <div className="max-w-5xl mx-auto">
          <h2 className="font-serif text-3xl md:text-4xl text-text-primary text-center mb-14">
            A fraction of what you&apos;d pay anywhere else.
          </h2>
          <div className="grid md:grid-cols-3 gap-6">
            {TIERS.map((tier) => {
              const isCurrent = subStatus === "active" && subTier === tier.key;
              return (
                <div
                  key={tier.name}
                  className={`rounded p-6 flex flex-col ${
                    isCurrent
                      ? "border-2 border-accent bg-background ring-1 ring-accent/10"
                      : tier.highlighted
                      ? "border-2 border-accent bg-background ring-1 ring-accent/10"
                      : "border border-border bg-background"
                  }`}
                >
                  {isCurrent && (
                    <span className="text-xs font-medium text-accent mb-3">Current Plan</span>
                  )}
                  {!isCurrent && tier.highlighted && (
                    <span className="text-xs font-medium text-accent mb-3">Recommended</span>
                  )}
                  <h3 className="text-sm font-medium text-text-primary">{tier.name}</h3>
                  <div className="mt-3 mb-5">
                    <span className="text-3xl font-serif text-text-primary tabular-nums">{tier.price}</span>
                    <span className="text-sm text-text-tertiary">{tier.period}</span>
                  </div>
                  <ul className="space-y-2.5 mb-6 flex-1">
                    {tier.features.map((feature) => (
                      <li key={feature} className="flex items-start gap-2 text-sm text-text-secondary">
                        <svg className="w-4 h-4 text-score-high shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M20 6L9 17l-5-5" />
                        </svg>
                        {feature}
                      </li>
                    ))}
                  </ul>

                  {/* Dynamic CTA */}
                  {isCurrent ? (
                    <button
                      disabled
                      className="block text-center py-2.5 text-sm font-medium rounded border border-accent/30 text-accent/60 cursor-not-allowed"
                    >
                      Current Plan
                    </button>
                  ) : session && subStatus === "active" ? (
                    <button
                      onClick={handlePortal}
                      className="block text-center py-2.5 text-sm font-medium rounded border border-border text-text-primary hover:border-text-tertiary transition"
                    >
                      Switch Plan
                    </button>
                  ) : session ? (
                    <button
                      onClick={() => handleCheckout(tier.key)}
                      disabled={!!checkoutLoading}
                      className={`block text-center py-2.5 text-sm font-medium rounded transition ${
                        tier.highlighted
                          ? "bg-accent text-white hover:bg-accent-hover disabled:opacity-50"
                          : "border border-border text-text-primary hover:border-text-tertiary disabled:opacity-50"
                      }`}
                    >
                      {checkoutLoading === tier.key ? "Redirecting..." : "Subscribe"}
                    </button>
                  ) : (
                    <Link
                      href="/auth/signup"
                      className={`block text-center py-2.5 text-sm font-medium rounded transition ${
                        tier.highlighted
                          ? "bg-accent text-white hover:bg-accent-hover"
                          : "border border-border text-text-primary hover:border-text-tertiary"
                      }`}
                    >
                      Get Started &rarr;
                    </Link>
                  )}
                </div>
              );
            })}
          </div>

          {/* Comparison line */}
          <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-4 sm:gap-8 text-sm">
            <span className="text-text-tertiary line-through">PitchBook: $20,000/yr</span>
            <span className="text-text-tertiary line-through">Crunchbase Pro: $5,000/yr</span>
            <span className="text-text-primary font-medium">Deep Thesis Starter: $240/yr</span>
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="px-6 lg:px-8 py-24 border-t border-border text-center">
        <h2 className="font-serif text-3xl md:text-4xl text-text-primary mb-4">
          Stop overpaying for deal intelligence.
        </h2>
        <p className="text-text-secondary text-lg mb-10 max-w-md mx-auto">
          Your first startup analysis is free. No credit card required.
        </p>
        <Link
          href="/analyze"
          className="inline-block px-8 py-3.5 bg-accent text-white text-sm font-medium rounded hover:bg-accent-hover transition"
        >
          Analyze a Startup — Free
        </Link>
      </section>
    </div>
  );
}
