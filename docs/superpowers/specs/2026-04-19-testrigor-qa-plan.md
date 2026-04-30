# DeepThesis Comprehensive QA Plan — TestRigor

> **Platform:** TestRigor (AI-powered, plain-English test automation)
> **Scope:** User-facing frontend + backend API verification (no admin panel)
> **Test Accounts:** 5 (3 free, 2 paid/unlimited)
> **Date:** 2026-04-19

---

## Test Accounts

| Variable | Email | Password | Plan |
|----------|-------|----------|------|
| Default (Auth) | `tester1@deepthesis.com` | `TestRigor2026` | Free |
| `free_user_2` | `tester2@deepthesis.com` | `TestRigor2026` | Free |
| `free_user_3` | `tester3@deepthesis.com` | `TestRigor2026` | Free |
| `paid_user_1` | `tester4@deepthesis.com` | `TestRigor2026` | Unlimited |
| `paid_user_2` | `tester5@deepthesis.com` | `TestRigor2026` | Unlimited |

---

## TestRigor Syntax Rules

- Use `open url` not `navigate to url`
- Use `login` only for default account (tester1) — for other accounts, manually enter credentials
- No `or` in check statements — use separate `check that` lines
- No descriptive phrases in click targets — keep them simple (e.g., `click on first link`)
- Use `wait X seconds` for plain waits, not `wait up to X seconds` without a condition
- Field names in `enter ... into "Field"` must match the actual placeholder or label text

---

## Test Suite 1: Auth & Onboarding

### TC-01: New User Signup and Authentication

```
open url "https://www.deepthesis.org"
check that page contains "DeepThesis"
click "Sign Up"
check that url contains "/auth/signup"
enter "qatester_auto@deepthesis.com" into "Email"
enter "TestRigor2026" into "Password"
enter "QA Auto Tester" into "Name"
click "Sign Up"
wait 15 seconds
check that page contains "Startups"
```

### TC-02: Login and Session Persistence

```
login
check that page contains "Startups"
click "Startups"
check that url contains "/startups"
click "Insights"
check that url contains "/insights"
click "Analyze"
check that url contains "/analyze"
```

### TC-03: Login with Wrong Password

```
open url "https://www.deepthesis.org"
click "Sign In"
enter "tester1@deepthesis.com" into "Email"
enter "WrongPassword999" into "Password"
click "Sign In"
check that page contains "Invalid"
check that url contains "/auth"
```

### TC-04: Logout Flow

```
login
click "Sign Out"
wait 10 seconds
check that page contains "Sign In"
```

---

## Test Suite 2: Startup Discovery & Detail

### TC-05: Startup Directory — Browse and Pagination

```
login
click "Startups"
check that url contains "/startups"
check that page contains "startups"
scroll down
click "Next"
check that url contains "page"
```

### TC-06: Startup Directory — Filter by Industry

```
login
click "Startups"
check that url contains "/startups"
click "Industry"
click "Fintech"
wait 5 seconds
check that url contains "industry"
```

### TC-07: Startup Directory — Filter by Stage

```
login
click "Startups"
check that url contains "/startups"
click "Stage"
click "Seed"
wait 5 seconds
check that url contains "stage"
```

### TC-08: Startup Directory — Search

```
login
click "Startups"
check that url contains "/startups"
enter "AI" into "Search"
wait 5 seconds
check that page contains "AI"
```

### TC-09: Startup Detail Page

```
login
click "Startups"
check that url contains "/startups"
click on first link
wait 5 seconds
check that url contains "/startups/"
check that page contains "Score"
scroll down
check that page contains "Funding"
```

### TC-10: Startup Detail — Scores and Sections

```
login
click "Startups"
check that url contains "/startups"
click on first link
wait 5 seconds
check that page contains "AI Score"
scroll down
check that page contains "Funding"
```

---

## Test Suite 3: Watchlist

### TC-11: Add Startup to Watchlist

```
login
click "Startups"
check that url contains "/startups"
click on first link
wait 5 seconds
check that url contains "/startups/"
click "Watch"
wait 3 seconds
```

### TC-12: View Watchlist Page

```
login
click "Watchlist"
check that url contains "/watchlist"
wait 5 seconds
check that page contains "Watchlist"
```

### TC-13: Remove from Watchlist

```
login
click "Watchlist"
check that url contains "/watchlist"
wait 5 seconds
click "Watch"
wait 3 seconds
```

---

## Test Suite 4: Pitch Analysis

### TC-14: Pitch Analysis — Upload Page Loads

```
login
click "Analyze"
check that url contains "/analyze"
check that page contains "Upload"
check that page contains "PDF"
```

### TC-15: Pitch Analysis — Paid User Upload

```
open url "https://www.deepthesis.org/auth/signin"
enter "tester4@deepthesis.com" into "Email"
enter "TestRigor2026" into "Password"
click "Sign In"
wait 5 seconds
click "Analyze"
check that url contains "/analyze"
enter "Test Startup QA" into "Company"
wait 3 seconds
```

### TC-16: Pitch Analysis — History Page

```
login
open url "https://www.deepthesis.org/analyze/history"
wait 5 seconds
check that page contains "History"
```

### TC-17: Pitch Analysis — Free User Limit Check

```
open url "https://www.deepthesis.org/auth/signin"
enter "tester3@deepthesis.com" into "Email"
enter "TestRigor2026" into "Password"
click "Sign In"
wait 5 seconds
click "Analyze"
check that url contains "/analyze"
check that page contains "Upload"
```

### TC-18: Pitch Analysis — Results Page Structure

```
open url "https://www.deepthesis.org/auth/signin"
enter "tester4@deepthesis.com" into "Email"
enter "TestRigor2026" into "Password"
click "Sign In"
wait 5 seconds
open url "https://www.deepthesis.org/analyze/history"
wait 5 seconds
click on first link
wait 5 seconds
check that page contains "Score"
```

---

## Test Suite 5: VC Quant Agent Chat (Analyst)

### TC-19: Analyst Chat — Page Loads

```
login
click "Insights"
check that url contains "/insights"
wait 5 seconds
check that page contains "Analyst"
```

### TC-20: Analyst Chat — Paid User Send Message

```
open url "https://www.deepthesis.org/auth/signin"
enter "tester4@deepthesis.com" into "Email"
enter "TestRigor2026" into "Password"
click "Sign In"
wait 5 seconds
click "Insights"
wait 5 seconds
click "New"
wait 3 seconds
enter "What are the top AI startups" into "Message"
click "Send"
wait 60 seconds
check that page contains "AI"
```

### TC-21: Analyst Chat — Conversation History

```
open url "https://www.deepthesis.org/auth/signin"
enter "tester4@deepthesis.com" into "Email"
enter "TestRigor2026" into "Password"
click "Sign In"
wait 5 seconds
click "Insights"
wait 5 seconds
check that page contains "conversation"
```

### TC-22: Analyst Chat — Share Conversation

```
open url "https://www.deepthesis.org/auth/signin"
enter "tester4@deepthesis.com" into "Email"
enter "TestRigor2026" into "Password"
click "Sign In"
wait 5 seconds
click "Insights"
wait 5 seconds
click "Share"
wait 3 seconds
check that page contains "link"
```

### TC-23: Analyst Chat — Free User Gate

```
open url "https://www.deepthesis.org/auth/signin"
enter "tester3@deepthesis.com" into "Email"
enter "TestRigor2026" into "Password"
click "Sign In"
wait 5 seconds
click "Insights"
wait 5 seconds
check that page contains "upgrade"
```

---

## Test Suite 6: Pitch Intelligence

### TC-24: Pitch Intelligence — Page Loads

```
login
click "Pitch Intelligence"
check that url contains "/pitch-intelligence"
wait 5 seconds
check that page contains "Pitch"
```

### TC-25: Pitch Intelligence — Paid User Access

```
open url "https://www.deepthesis.org/auth/signin"
enter "tester5@deepthesis.com" into "Email"
enter "TestRigor2026" into "Password"
click "Sign In"
wait 5 seconds
click "Pitch Intelligence"
wait 5 seconds
check that page contains "Upload"
```

### TC-26: Pitch Intelligence — Paste Transcript

```
open url "https://www.deepthesis.org/auth/signin"
enter "tester5@deepthesis.com" into "Email"
enter "TestRigor2026" into "Password"
click "Sign In"
wait 5 seconds
click "Pitch Intelligence"
wait 5 seconds
click "Transcript"
wait 3 seconds
enter "We are building an AI platform for venture capital due diligence" into "Transcript"
```

### TC-27: Pitch Intelligence — Free User Gate

```
open url "https://www.deepthesis.org/auth/signin"
enter "tester3@deepthesis.com" into "Email"
enter "TestRigor2026" into "Password"
click "Sign In"
wait 5 seconds
click "Pitch Intelligence"
wait 5 seconds
check that page contains "upgrade"
```

---

## Test Suite 7: Insights Dashboard

### TC-28: Insights Dashboard — Page Loads

```
login
click "Insights"
wait 10 seconds
check that url contains "/insights"
check that page contains "Insights"
```

### TC-29: Insights Dashboard — Summary Stats

```
login
click "Insights"
wait 10 seconds
check that page contains "Total"
scroll down
check that page contains "Funding"
```

### TC-30: Insights Dashboard — Filters

```
login
click "Insights"
wait 10 seconds
click "Industry"
wait 3 seconds
click "Fintech"
wait 5 seconds
```

---

## Test Suite 8: Billing & Subscription

### TC-31: Billing — Free User See Plans

```
login
open url "https://www.deepthesis.org/billing"
wait 5 seconds
check that page contains "Free"
check that page contains "Starter"
check that page contains "Professional"
```

### TC-32: Billing — Upgrade Button Exists

```
login
open url "https://www.deepthesis.org/billing"
wait 5 seconds
check that page contains "Upgrade"
```

### TC-33: Billing — Paid User Active Plan

```
open url "https://www.deepthesis.org/auth/signin"
enter "tester4@deepthesis.com" into "Email"
enter "TestRigor2026" into "Password"
click "Sign In"
wait 5 seconds
open url "https://www.deepthesis.org/billing"
wait 5 seconds
check that page contains "Unlimited"
```

### TC-34: Billing — Landing Page Pricing

```
open url "https://www.deepthesis.org"
scroll down
check that page contains "Pricing"
check that page contains "Free"
check that page contains "Professional"
```

---

## Test Suite 9: Profile & Expert Application

### TC-35: Profile — View and Edit

```
login
open url "https://www.deepthesis.org/profile"
wait 5 seconds
check that page contains "Profile"
check that page contains "tester1"
```

### TC-36: Profile — Select Ecosystem Role

```
login
open url "https://www.deepthesis.org/profile"
wait 5 seconds
click "Ecosystem Role"
click "Investor"
click "Save"
wait 5 seconds
check that page contains "Investor"
```

### TC-37: Expert Application — Page Loads

```
login
open url "https://www.deepthesis.org/experts/apply"
wait 5 seconds
check that page contains "Expert"
check that page contains "Bio"
```

### TC-38: Expert Application — Submit

```
open url "https://www.deepthesis.org/auth/signin"
enter "tester2@deepthesis.com" into "Email"
enter "TestRigor2026" into "Password"
click "Sign In"
wait 5 seconds
open url "https://www.deepthesis.org/experts/apply"
wait 5 seconds
enter "Venture capital analyst with 5 years experience in fintech" into "Bio"
enter "5" into "Years"
click "Apply"
wait 10 seconds
check that page contains "submitted"
```

---

## Test Suite 10: Feedback Widget

### TC-39: Feedback Widget — Bubble Visible

```
login
wait 5 seconds
check that page contains "Share feedback"
```

### TC-40: Feedback Widget — Open and Close

```
login
wait 5 seconds
click "Share feedback"
wait 3 seconds
check that page contains "Feedback"
click "Close feedback"
wait 3 seconds
```

### TC-41: Feedback Widget — Send Message

```
login
wait 5 seconds
click "Share feedback"
wait 3 seconds
enter "The startup filtering is confusing" into "feedback"
click "Send"
wait 30 seconds
check that page contains "feedback"
```

### TC-42: Feedback Widget — Multi Turn Conversation

```
login
wait 5 seconds
click "Share feedback"
wait 3 seconds
enter "I found a bug on the startups page" into "feedback"
click "Send"
wait 30 seconds
enter "The results do not update when I filter" into "feedback"
click "Send"
wait 30 seconds
```

---

## Test Suite 11: Notifications

### TC-43: Notifications — Bell Visible

```
open url "https://www.deepthesis.org/auth/signin"
enter "tester4@deepthesis.com" into "Email"
enter "TestRigor2026" into "Password"
click "Sign In"
wait 5 seconds
check that page contains "Notifications"
```

### TC-44: Notifications — Open Dropdown

```
open url "https://www.deepthesis.org/auth/signin"
enter "tester4@deepthesis.com" into "Email"
enter "TestRigor2026" into "Password"
click "Sign In"
wait 5 seconds
click "Notifications"
wait 3 seconds
check that page contains "notification"
```

---

## Test Execution Strategy

### Priority Order
1. **P0 — Run first:** Auth (TC-01 to TC-04), Startup Discovery (TC-05 to TC-10), Analyst Chat (TC-19 to TC-23), Pitch Analysis (TC-14 to TC-18)
2. **P1 — Run second:** Watchlist (TC-11 to TC-13), Pitch Intelligence (TC-24 to TC-27), Insights (TC-28 to TC-30), Billing (TC-31 to TC-34)
3. **P2 — Run third:** Profile (TC-35 to TC-38), Feedback (TC-39 to TC-42), Notifications (TC-43 to TC-44)

### Scheduling
- **Nightly:** Full suite (all 44 test cases)
- **Post-deploy:** P0 suite only (smoke test)
- **Weekly:** Full suite on Chrome + Firefox

### Known Limitations
- **SSE Streaming (Analyst, Feedback):** TestRigor verifies final result appeared, not token-by-token streaming. Tests use long waits for streaming responses.
- **Stripe Checkout:** TC-32 verifies the upgrade button exists but cannot complete payment. Paid account testing relies on pre-provisioned accounts (tester4, tester5 with promo code).
- **File Upload:** Requires test files uploaded to TestRigor's Test Data. Not included in current test cases — add when test files are available.
- **Dynamic Content:** Startup names, scores, and counts may change. Tests check for structural elements rather than specific values.
