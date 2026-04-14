# Landing Page Redesign — Design Spec

**Date:** 2026-04-14
**Approach:** "The Unfair Advantage" — lead with the pain point of overpriced data tools, position Deep Thesis as institutional-grade intelligence at angel investor pricing. Bolder and more data-forward than current page while keeping the existing color palette (rust accent, warm neutrals) and typography (Instrument Serif + Inter).

**Target audience:** Small angel investors, scouts, solo GPs, emerging managers.

**File to modify:** `frontend/app/page.tsx` (landing page only — no other pages change)

---

## Section 1: Hero

**Headline (serif, large):** "Institutional-grade deal intelligence. Angel investor price."

**Subhead:** Deep Thesis aggregates data from 1,000+ buy-side VC transactions, secondaries markets, Crunchbase, PitchBook, and an army of AI agents — so you can make quantitative investment decisions without a $20K/yr data subscription.

**CTAs:**
- Primary button: "Analyze a Startup — Free" → `/analyze`
- Secondary button: "See Pricing" → scrolls to pricing section (`#pricing`)

**Stat bar** (muted background row beneath CTAs):
- `1,000+ transactions tracked`
- `2,800+ companies profiled`
- `8 AI agents per analysis`

---

## Section 2: The Problem

**Headline (serif):** "The math doesn't work."

**Two-column layout (stacked on mobile):**

Left column — the problem:
- PitchBook: ~$20,000/yr
- Crunchbase Pro: ~$5,000/yr
- Your average check size: $25K–$50K
- "You shouldn't need to spend more on data than you deploy in a deal."

Right column — the shift:
- "Deep Thesis was built for investors who write their own checks — angels, scouts, solo GPs, and emerging managers who need real data, not a Bloomberg terminal budget."

No CTA in this section.

---

## Section 3: What Powers the Platform

**Headline (serif):** "Data you can't Google."

**2x2 card grid (single column on mobile):**

1. **Buy-Side Transaction Data** — "1,000+ closed VC transactions with pricing, terms, and outcomes from actual buy-side deals."
2. **VC Secondaries Market** — "Real secondary market pricing and liquidity data on venture-backed companies — the layer most platforms ignore."
3. **Crunchbase + PitchBook** — "Funding rounds, investors, team data, and company profiles aggregated and cross-referenced."
4. **AI Agent Network** — "An army of specialized agents that continuously evaluate companies across 8 dimensions — market, team, traction, technology, competition, financials, and more."

**Below the grid:** "All of this feeds into every company profile, every analysis, and every report you generate."

---

## Section 4: Three Core Tools

**Headline (serif):** "Search. Analyze. Reason."

**Three feature blocks, stacked vertically:**

1. **Company Search & Discovery**
   - "Browse 2,800+ venture-backed companies with structured profiles — founders, funding history, investors, tech stack, competitors. Filter by stage, industry, state, AI score. Every profile backed by multi-source data."
   - Link: "Explore companies →" → `/startups`

2. **Startup Analysis**
   - "Upload a pitch deck and documents. Eight AI agents independently evaluate the company across market, team, traction, technology, competition, GTM, financials, and problem/solution fit. Get a scored report with fundraising projections — your first analysis is free."
   - Link: "Try it free →" → `/analyze`

3. **VC Quant Agent**
   - "Ask questions across our entire dataset. Draft investment memos. Run quantitative comparisons. Generate reports grounded in real transaction data, not vibes. The analyst you'd hire for $150K — available on demand."
   - Link: "Try it →" → `/agent` (or appropriate route)

---

## Section 5: Pricing

**Anchor ID:** `#pricing`

**Headline (serif):** "A fraction of what you'd pay anywhere else."

**Three pricing cards side by side (stacked on mobile):**

### Starter — $19.99/mo
- 10 startup analyses / month
- 15 reports generated / month
- Unlimited company search & profiles
- VC Quant Agent access
- CTA: "Start free →"

### Professional — $200/mo *(highlighted as recommended)*
- 50 startup analyses / month
- Unlimited reports
- Unlimited company search & profiles
- VC Quant Agent access
- Priority processing
- CTA: "Get started →"

### Unlimited — $500/mo
- Unlimited everything
- VC Quant Agent access
- Priority processing
- API access
- CTA: "Contact us →"

**Comparison line below cards:** "PitchBook: $20,000/yr. Crunchbase Pro: $5,000/yr. Deep Thesis Starter: $240/yr."

---

## Section 6: Final CTA

**Headline (serif):** "Stop overpaying for deal intelligence."

**Subhead:** "Your first startup analysis is free. No credit card required."

**Primary CTA button:** "Analyze a Startup — Free" → `/analyze`

---

## Visual Direction

- **Same palette:** Rust accent (#B8553A), warm off-white background (#FAFAF8), white surfaces, warm borders (#E8E6E3)
- **Same fonts:** Instrument Serif for headlines, Inter for body
- **Bolder than current:** Larger hero type, more contrast, data-forward stat bar, pricing cards with clear visual hierarchy
- **More urgency:** Comparative pricing language, problem framing, direct CTAs
- **Cards use existing pattern:** `rounded border border-border bg-surface p-5` with hover states
- **Professional card highlighted:** Accent border or subtle accent background to mark it as recommended
- **Responsive:** All grids collapse to single column on mobile, CTAs stack vertically

## What This Replaces

The entire content of `frontend/app/page.tsx` is replaced. The current page has:
- Generic "Transparency into venture-backed companies" hero
- Three pillars section
- "Everything you need on every deal" feature grid
- Featured startups grid (server-fetched)
- Pitch analysis CTA
- Generic closing CTA

The featured startups grid is removed from the landing page. Users discover companies via the `/startups` page instead. The new page is a static marketing page — no server-side data fetching required. It can be a client component or a simple server component with no async data.

## What This Does NOT Change

- No changes to `/startups`, `/analyze`, `/insights`, or any other page
- No changes to the design system, color tokens, fonts, or global CSS
- No changes to the Navbar or layout
- No backend changes
