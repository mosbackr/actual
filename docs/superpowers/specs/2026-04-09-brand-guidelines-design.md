# Acutal Brand Guidelines

## Positioning

Editorial authority meets investment intelligence. Acutal looks more like the Financial Times or The Economist than a SaaS dashboard. Light, typographic, data-rich. Designed for institutional investors (VCs, family offices) who value depth and credibility over flash.

## Color Palette

### Core

| Token | Hex | Usage |
|-------|-----|-------|
| `background` | `#FAFAF8` | Page background — warm off-white, not sterile |
| `surface` | `#FFFFFF` | Cards, panels, elevated surfaces |
| `text-primary` | `#1A1A1A` | Headlines, primary body text |
| `text-secondary` | `#6B6B6B` | Supporting copy, metadata |
| `text-tertiary` | `#9B9B9B` | Captions, timestamps, disabled states |
| `border` | `#E8E6E3` | Dividers, card borders — warm gray |
| `accent` | `#B8553A` | Brand accent — muted terracotta. Links, active states, CTAs |
| `accent-hover` | `#9C4530` | Darker accent for hover/pressed states |

### Score Colors

| Token | Hex | Usage |
|-------|-----|-------|
| `score-high` | `#2D6A4F` | Scores 70+ — deep forest green |
| `score-mid` | `#B8860B` | Scores 40-69 — dark goldenrod |
| `score-low` | `#A23B3B` | Scores below 40 — muted crimson |

Score colors are applied only to the score number itself and the thin dimension bar charts. Everything else stays neutral. No colored backgrounds, badges, or circles.

### Interactive States

| State | Treatment |
|-------|-----------|
| Hover (links/buttons) | Accent darkens to `accent-hover`. Underline appears on text links. |
| Focus | 2px ring in `accent` with 2px offset |
| Active nav item | `text-primary` weight `font-semibold`, bottom border in `accent` |
| Disabled | `text-tertiary`, no pointer events |

## Typography

### Typefaces

| Role | Font | Source | Fallback |
|------|------|--------|----------|
| Headlines | Instrument Serif | Google Fonts | Georgia, serif |
| Body / UI | Inter | Google Fonts (already in use) | system-ui, sans-serif |

Instrument Serif is used for page titles, startup names, section headers, and the score number. Inter handles everything else: body text, labels, buttons, navigation, form inputs.

### Scale

| Token | Size | Weight | Font | Usage |
|-------|------|--------|------|-------|
| `display` | 36px / 2.25rem | 400 | Instrument Serif | Page titles ("Startups", "Due Diligence") |
| `headline` | 24px / 1.5rem | 400 | Instrument Serif | Startup names, section headers |
| `title` | 20px / 1.25rem | 400 | Instrument Serif | Card titles, subsection headers |
| `body` | 16px / 1rem | 400 | Inter | Default body text |
| `body-small` | 14px / 0.875rem | 400 | Inter | Secondary descriptions, table cells |
| `caption` | 12px / 0.75rem | 500 | Inter | Labels, metadata, timestamps |
| `score` | 32px / 2rem | 400 | Instrument Serif | Score numbers — uses tabular numerals from Inter for alignment in tables |

Serif headlines should never be bold. Their natural weight carries enough presence. Use weight variation only in the sans-serif (Inter) for emphasis.

### Tabular Numerals

All numeric data in tables and score displays must use tabular (monospaced) numerals for column alignment. In Tailwind, apply `tabular-nums` to containers with numeric data. Inter supports this natively via OpenType features.

## Score System

The score is a doorway to the analysis, not a badge.

### Display Treatment

- The composite score is shown as a large serif number colored by range (green/gold/red from score palette)
- Next to the score: a compact horizontal bar chart showing each dimension's contribution — thin bars, neutral gray with the dimension's score portion filled in score color
- No colored circles, badges, or background fills around the score
- The number alone communicates severity; the bars communicate composition

### Expansion Behavior

- Default state shows composite score + dimension summary bars
- Click or hover expands to full dimension breakdown: dimension name, individual score, expert consensus notes
- Expansion is inline (pushes content down) on detail pages, modal/popover on list views

### Score in Tables

- Right-aligned, tabular numerals, colored by range
- No background color on the cell — just the number color
- Sortable column

## Layout Principles

### Grid

- Max content width: `max-w-6xl` (72rem / 1152px), centered
- Page padding: `px-6 lg:px-8`
- Content uses a 12-column implicit grid via Tailwind's grid utilities
- Generous vertical spacing between sections: `space-y-12` or `gap-12` at section level

### Whitespace

Whitespace is a design element, not wasted space. Minimum spacing between content blocks is `gap-6`. Cards have internal padding of `p-6` minimum. Sections separated by `py-12` or a thin `border-b` divider.

### Cards

- Minimal chrome: 1px `border` in `border` color, no rounded corners larger than `rounded` (4px), no shadows
- Or no border at all — use spacing and background (`surface` on `background`) to create separation
- No gradient backgrounds, no colored headers

### Navigation

- Top horizontal navbar, full-width with content constrained to max-width
- Nav items are plain text links in `text-secondary`, active item in `text-primary` with `font-semibold` and a bottom border accent
- No pill-shaped active indicators, no background highlights

### Tables

- Clean horizontal rules only (no vertical borders, no zebra striping)
- Header row in `caption` style: small, medium weight, `text-secondary`, uppercase tracking
- Generous row padding: `py-4`
- Hover state: subtle background shift to `#F5F5F3`

## Brand Voice in UI

- No exclamation marks in interface copy
- No emoji
- No casual greetings ("Hey there!", "Welcome back!")
- Concise, declarative labels: "12 startups pending review" not "You have 12 new startups to check out!"
- Section headers read like newspaper section heads
- Error messages are direct: "Could not load startups" not "Oops! Something went wrong"
- Empty states are informative: "No startups match this filter" not "Nothing here yet!"

## Iconography

- Line icons only — no filled/solid icons
- Stroke width: 1.5px (matches the editorial lightness)
- Source: Lucide icons (already compatible with React, consistent 24x24 grid)
- Icons are secondary to text — used for reinforcement, never as the sole label

## Logo

- Text-only wordmark: "Acutal" set in Instrument Serif at display size
- The lowercase "a" at the start is distinctive enough at this stage — no symbol/icon logo needed yet
- Color: `text-primary` on light backgrounds
- Minimum clear space: the height of the capital "A" on all sides

## Responsive Behavior

- Mobile: single column, full-width cards, hamburger nav
- Tablet: two-column grid for card layouts
- Desktop: three-column grid, full navigation visible
- Score expansion behavior stays inline on all breakpoints
- Tables become horizontally scrollable on mobile with a fade indicator at the edge

## What This Spec Does NOT Cover

- Specific page layouts (homepage, startup detail, expert profile) — these are implementation concerns
- Animation/motion design — keep transitions to CSS defaults (150ms ease) for now
- Dark mode — not planned. The light editorial look is the brand.
- Marketing site vs. app distinction — same visual language for both at this stage
