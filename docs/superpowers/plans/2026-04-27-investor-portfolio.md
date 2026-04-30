# Investor Portfolio Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let investors claim their profile and manage a portfolio of companies on their score page, creating a verified investor-startup relationship graph.

**Architecture:** New `portfolio_companies` table + `user_id` FK on investors. New API router for portfolio CRUD, claim, and suggestions. Extend the existing `/score/[id]` frontend page with portfolio section, add-company modal, and claim flow. Add "Add to Portfolio" button on startup detail pages. Add "Portfolio" nav link for investor users.

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL, Next.js (App Router), Tailwind v4, next-auth

---

## File Structure

**Backend — Create:**
- `backend/app/models/portfolio.py` — PortfolioCompany model
- `backend/app/api/investor_portfolio.py` — Portfolio CRUD + claim + suggestions router

**Backend — Modify:**
- `backend/app/models/investor.py` — Add `user_id` column to Investor
- `backend/app/main.py` — Register new router

**Frontend — Create:**
- `frontend/app/score/[id]/portfolio-section.tsx` — Portfolio grid (owner + visitor views)
- `frontend/app/score/[id]/add-company-modal.tsx` — Add company modal with type-ahead
- `frontend/app/score/[id]/claim-banner.tsx` — Claim profile banner + suggested portfolio flow
- `frontend/app/startups/[slug]/portfolio-button.tsx` — "Add to Portfolio" button

**Frontend — Modify:**
- `frontend/lib/api.ts` — Add portfolio API methods
- `frontend/app/score/[id]/page.tsx` — Import and render new components
- `frontend/app/startups/[slug]/page.tsx` — Add PortfolioButton next to WatchButton
- `frontend/components/Navbar.tsx` — Add "Portfolio" link for investor users

---

### Task 1: PortfolioCompany Model + user_id on Investor

**Files:**
- Create: `backend/app/models/portfolio.py`
- Modify: `backend/app/models/investor.py:1-63`

- [ ] **Step 1: Create the PortfolioCompany model**

Create `backend/app/models/portfolio.py`:

```python
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.industry import Base


class PortfolioCompany(Base):
    __tablename__ = "portfolio_companies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    investor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("investors.id", ondelete="CASCADE"),
        nullable=False,
    )
    startup_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("startups.id", ondelete="SET NULL"),
        nullable=True,
    )
    company_name: Mapped[str] = mapped_column(String(300), nullable=False)
    company_website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    investment_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    round_stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    check_size: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_lead: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    board_seat: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'active'")
    )
    exit_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    exit_multiple: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_public: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("investor_id", "company_name", name="uq_portfolio_investor_company"),
    )
```

- [ ] **Step 2: Add user_id column to Investor model**

In `backend/app/models/investor.py`, add this import and column after the `updated_at` field (before `__table_args__`):

Add to imports at line 5:
```python
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, text
```

Add column after `updated_at` (after line 59):
```python
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )
```

- [ ] **Step 3: Create tables in production database via SQL**

Run these SQL statements on the production database:

```sql
-- Add user_id to investors
ALTER TABLE investors ADD COLUMN user_id UUID UNIQUE REFERENCES users(id) ON DELETE SET NULL;

-- Create portfolio_companies table
CREATE TABLE portfolio_companies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investor_id UUID NOT NULL REFERENCES investors(id) ON DELETE CASCADE,
    startup_id UUID REFERENCES startups(id) ON DELETE SET NULL,
    company_name VARCHAR(300) NOT NULL,
    company_website VARCHAR(500),
    investment_date DATE,
    round_stage VARCHAR(50),
    check_size VARCHAR(100),
    is_lead BOOLEAN NOT NULL DEFAULT false,
    board_seat BOOLEAN NOT NULL DEFAULT false,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    exit_type VARCHAR(20),
    exit_multiple FLOAT,
    is_public BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_portfolio_investor_company UNIQUE (investor_id, company_name)
);

CREATE INDEX ix_portfolio_companies_investor_id ON portfolio_companies(investor_id);
CREATE INDEX ix_portfolio_companies_startup_id ON portfolio_companies(startup_id);
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/portfolio.py backend/app/models/investor.py
git commit -m "feat: add PortfolioCompany model and user_id on Investor"
```

---

### Task 2: Portfolio API Router — CRUD + Claim + Suggestions

**Files:**
- Create: `backend/app/api/investor_portfolio.py`
- Modify: `backend/app/main.py:75-139`

- [ ] **Step 1: Create the portfolio API router**

Create `backend/app/api/investor_portfolio.py`:

```python
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.investor import Investor
from app.models.portfolio import PortfolioCompany
from app.models.startup import Startup
from app.models.user import User, UserRole

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────────

class PortfolioCreateBody(BaseModel):
    company_name: str
    startup_id: str | None = None
    company_website: str | None = None
    investment_date: date | None = None
    round_stage: str | None = None
    check_size: str | None = None
    is_lead: bool = False
    board_seat: bool = False
    status: str = "active"
    exit_type: str | None = None
    exit_multiple: float | None = None
    is_public: bool = True


class PortfolioUpdateBody(BaseModel):
    company_name: str | None = None
    startup_id: str | None = None
    company_website: str | None = None
    investment_date: date | None = None
    round_stage: str | None = None
    check_size: str | None = None
    is_lead: bool | None = None
    board_seat: bool | None = None
    status: str | None = None
    exit_type: str | None = None
    exit_multiple: float | None = None
    is_public: bool | None = None


# ── Helpers ────────────────────────────────────────────────────────────────

def _portfolio_response(pc: PortfolioCompany, startup: Startup | None = None) -> dict:
    result = {
        "id": str(pc.id),
        "investor_id": str(pc.investor_id),
        "startup_id": str(pc.startup_id) if pc.startup_id else None,
        "company_name": pc.company_name,
        "company_website": pc.company_website,
        "investment_date": pc.investment_date.isoformat() if pc.investment_date else None,
        "round_stage": pc.round_stage,
        "check_size": pc.check_size,
        "is_lead": pc.is_lead,
        "board_seat": pc.board_seat,
        "status": pc.status,
        "exit_type": pc.exit_type,
        "exit_multiple": pc.exit_multiple,
        "is_public": pc.is_public,
        "startup_slug": None,
        "startup_logo_url": None,
        "startup_stage": None,
    }
    if startup:
        result["startup_slug"] = startup.slug
        result["startup_logo_url"] = startup.logo_url
        result["startup_stage"] = startup.stage.value if startup.stage else None
    return result


async def _get_investor_and_check_owner(
    investor_id: uuid.UUID, user: User, db: AsyncSession
) -> Investor:
    investor = await db.get(Investor, investor_id)
    if not investor:
        raise HTTPException(status_code=404, detail="Investor not found")
    if investor.user_id != user.id and user.role != UserRole.superadmin:
        raise HTTPException(status_code=403, detail="Not your profile")
    return investor


# ── List Portfolio ─────────────────────────────────────────────────────────

@router.get("/api/investors/{investor_id}/portfolio")
async def list_portfolio(
    investor_id: uuid.UUID,
    user: User | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    investor = await db.get(Investor, investor_id)
    if not investor:
        raise HTTPException(status_code=404, detail="Investor not found")

    is_owner = (
        user
        and investor.user_id
        and (investor.user_id == user.id or user.role == UserRole.superadmin)
    )

    query = (
        select(PortfolioCompany, Startup)
        .outerjoin(Startup, PortfolioCompany.startup_id == Startup.id)
        .where(PortfolioCompany.investor_id == investor_id)
        .order_by(PortfolioCompany.created_at.desc())
    )

    if not is_owner:
        query = query.where(PortfolioCompany.is_public == True)

    result = await db.execute(query)
    rows = result.all()

    return {
        "items": [_portfolio_response(pc, startup) for pc, startup in rows],
        "is_owner": bool(is_owner),
    }


# ── Add Portfolio Company ──────────────────────────────────────────────────

@router.post("/api/investors/{investor_id}/portfolio")
async def add_portfolio_company(
    investor_id: uuid.UUID,
    body: PortfolioCreateBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_investor_and_check_owner(investor_id, user, db)

    # Validate startup_id if provided
    startup_id_val = None
    if body.startup_id:
        startup = await db.get(Startup, uuid.UUID(body.startup_id))
        if not startup:
            raise HTTPException(status_code=400, detail="Startup not found")
        startup_id_val = startup.id

    # Check for duplicate
    existing = await db.execute(
        select(PortfolioCompany).where(
            PortfolioCompany.investor_id == investor_id,
            PortfolioCompany.company_name == body.company_name,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Company already in portfolio")

    pc = PortfolioCompany(
        investor_id=investor_id,
        startup_id=startup_id_val,
        company_name=body.company_name,
        company_website=body.company_website,
        investment_date=body.investment_date,
        round_stage=body.round_stage,
        check_size=body.check_size,
        is_lead=body.is_lead,
        board_seat=body.board_seat,
        status=body.status,
        exit_type=body.exit_type,
        exit_multiple=body.exit_multiple,
        is_public=body.is_public,
    )
    db.add(pc)
    await db.commit()
    await db.refresh(pc)

    # Load linked startup for response
    startup = await db.get(Startup, pc.startup_id) if pc.startup_id else None
    return _portfolio_response(pc, startup)


# ── Update Portfolio Company ───────────────────────────────────────────────

@router.put("/api/investors/{investor_id}/portfolio/{portfolio_id}")
async def update_portfolio_company(
    investor_id: uuid.UUID,
    portfolio_id: uuid.UUID,
    body: PortfolioUpdateBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_investor_and_check_owner(investor_id, user, db)

    pc = await db.get(PortfolioCompany, portfolio_id)
    if not pc or pc.investor_id != investor_id:
        raise HTTPException(status_code=404, detail="Portfolio entry not found")

    update_data = body.model_dump(exclude_unset=True)

    if "startup_id" in update_data and update_data["startup_id"]:
        startup = await db.get(Startup, uuid.UUID(update_data["startup_id"]))
        if not startup:
            raise HTTPException(status_code=400, detail="Startup not found")
        update_data["startup_id"] = startup.id

    for key, value in update_data.items():
        setattr(pc, key, value)

    await db.commit()
    await db.refresh(pc)

    startup = await db.get(Startup, pc.startup_id) if pc.startup_id else None
    return _portfolio_response(pc, startup)


# ── Delete Portfolio Company ───────────────────────────────────────────────

@router.delete("/api/investors/{investor_id}/portfolio/{portfolio_id}", status_code=204)
async def delete_portfolio_company(
    investor_id: uuid.UUID,
    portfolio_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_investor_and_check_owner(investor_id, user, db)

    pc = await db.get(PortfolioCompany, portfolio_id)
    if not pc or pc.investor_id != investor_id:
        raise HTTPException(status_code=404, detail="Portfolio entry not found")

    await db.delete(pc)
    await db.commit()


# ── Claim Profile ──────────────────────────────────────────────────────────

@router.post("/api/investors/claim")
async def claim_investor_profile(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Check if user already has a claimed profile
    result = await db.execute(
        select(Investor).where(Investor.user_id == user.id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return {
            "investor_id": str(existing.id),
            "firm_name": existing.firm_name,
            "partner_name": existing.partner_name,
            "already_claimed": True,
        }

    # Find investor by email match
    result = await db.execute(
        select(Investor).where(
            Investor.email.isnot(None),
            Investor.user_id.is_(None),
            Investor.email.ilike(user.email),
        )
    )
    investor = result.scalar_one_or_none()
    if not investor:
        raise HTTPException(status_code=404, detail="No investor profile matches your email")

    investor.user_id = user.id
    user.role = UserRole.investor
    await db.commit()

    return {
        "investor_id": str(investor.id),
        "firm_name": investor.firm_name,
        "partner_name": investor.partner_name,
        "already_claimed": False,
    }


# ── Suggested Portfolio ────────────────────────────────────────────────────

@router.get("/api/investors/{investor_id}/suggested-portfolio")
async def get_suggested_portfolio(
    investor_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    investor = await _get_investor_and_check_owner(investor_id, user, db)

    recent = investor.recent_investments or []
    if not recent:
        return {"suggestions": []}

    suggestions = []
    for company_name in recent:
        if not isinstance(company_name, str) or not company_name.strip():
            continue
        name = company_name.strip()

        # Try fuzzy match against startups
        result = await db.execute(
            select(Startup)
            .where(Startup.name.ilike(f"%{name}%"))
            .limit(1)
        )
        startup = result.scalar_one_or_none()

        suggestions.append({
            "company_name": name,
            "matched_startup": {
                "id": str(startup.id),
                "slug": startup.slug,
                "name": startup.name,
                "logo_url": startup.logo_url,
                "stage": startup.stage.value if startup.stage else None,
            } if startup else None,
        })

    return {"suggestions": suggestions}
```

- [ ] **Step 2: Register the router in main.py**

Add these lines to `backend/app/main.py`:

After line 77 (the `from app.api.zoom import router as zoom_router` line), add:
```python
from app.api.investor_portfolio import router as investor_portfolio_router
```

After line 139 (the `app.include_router(zoom_router)` line), add:
```python
app.include_router(investor_portfolio_router)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/investor_portfolio.py backend/app/main.py
git commit -m "feat: add investor portfolio API — CRUD, claim, suggestions"
```

---

### Task 3: Frontend API Client — Portfolio Methods

**Files:**
- Modify: `frontend/lib/api.ts:584`

- [ ] **Step 1: Add portfolio methods to the api object**

Add the following block at the end of the `api` object in `frontend/lib/api.ts`, before the closing `};`:

```typescript
  // ── Portfolio ─────────────────────────────────────────────────────────

  async getPortfolio(token: string, investorId: string) {
    return apiFetch<{
      items: Array<{
        id: string;
        investor_id: string;
        startup_id: string | null;
        company_name: string;
        company_website: string | null;
        investment_date: string | null;
        round_stage: string | null;
        check_size: string | null;
        is_lead: boolean;
        board_seat: boolean;
        status: string;
        exit_type: string | null;
        exit_multiple: number | null;
        is_public: boolean;
        startup_slug: string | null;
        startup_logo_url: string | null;
        startup_stage: string | null;
      }>;
      is_owner: boolean;
    }>(`/api/investors/${investorId}/portfolio`, {
      headers: authHeaders(token),
    });
  },

  async addPortfolioCompany(
    token: string,
    investorId: string,
    body: {
      company_name: string;
      startup_id?: string;
      company_website?: string;
      investment_date?: string;
      round_stage?: string;
      check_size?: string;
      is_lead?: boolean;
      board_seat?: boolean;
      status?: string;
      is_public?: boolean;
    }
  ) {
    return apiFetch<Record<string, unknown>>(
      `/api/investors/${investorId}/portfolio`,
      {
        method: "POST",
        headers: authHeaders(token),
        body: JSON.stringify(body),
      }
    );
  },

  async updatePortfolioCompany(
    token: string,
    investorId: string,
    portfolioId: string,
    body: Record<string, unknown>
  ) {
    return apiFetch<Record<string, unknown>>(
      `/api/investors/${investorId}/portfolio/${portfolioId}`,
      {
        method: "PUT",
        headers: authHeaders(token),
        body: JSON.stringify(body),
      }
    );
  },

  async deletePortfolioCompany(token: string, investorId: string, portfolioId: string) {
    await fetch(`${API_URL}/api/investors/${investorId}/portfolio/${portfolioId}`, {
      method: "DELETE",
      headers: { ...authHeaders(token) },
    });
  },

  async claimInvestorProfile(token: string) {
    return apiFetch<{
      investor_id: string;
      firm_name: string;
      partner_name: string;
      already_claimed: boolean;
    }>("/api/investors/claim", {
      method: "POST",
      headers: authHeaders(token),
    });
  },

  async getSuggestedPortfolio(token: string, investorId: string) {
    return apiFetch<{
      suggestions: Array<{
        company_name: string;
        matched_startup: {
          id: string;
          slug: string;
          name: string;
          logo_url: string | null;
          stage: string | null;
        } | null;
      }>;
    }>(`/api/investors/${investorId}/suggested-portfolio`, {
      headers: authHeaders(token),
    });
  },
```

- [ ] **Step 2: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat: add portfolio API methods to frontend client"
```

---

### Task 4: Claim Banner Component

**Files:**
- Create: `frontend/app/score/[id]/claim-banner.tsx`

- [ ] **Step 1: Create the claim banner component**

Create `frontend/app/score/[id]/claim-banner.tsx`:

```tsx
"use client";

import { useState } from "react";
import { api } from "@/lib/api";

const stageLabels: Record<string, string> = {
  pre_seed: "Pre-Seed", seed: "Seed", series_a: "Series A",
  series_b: "Series B", series_c: "Series C", growth: "Growth",
  public: "Public",
};

interface Suggestion {
  company_name: string;
  matched_startup: {
    id: string;
    slug: string;
    name: string;
    logo_url: string | null;
    stage: string | null;
  } | null;
}

export function ClaimBanner({
  investorId,
  token,
  onClaimed,
}: {
  investorId: string;
  token: string;
  onClaimed: () => void;
}) {
  const [claiming, setClaiming] = useState(false);
  const [suggestions, setSuggestions] = useState<Suggestion[] | null>(null);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);

  async function handleClaim() {
    setClaiming(true);
    try {
      const result = await api.claimInvestorProfile(token);
      if (result.already_claimed) {
        onClaimed();
        return;
      }
      // Load suggestions
      const { suggestions: sugs } = await api.getSuggestedPortfolio(token, result.investor_id);
      if (sugs.length === 0) {
        onClaimed();
        return;
      }
      setSuggestions(sugs);
      setChecked(new Set(sugs.map((s) => s.company_name)));
    } catch {
      // If claim fails (404 = no match), just hide the banner
    }
    setClaiming(false);
  }

  async function handleConfirm() {
    setSaving(true);
    for (const sug of suggestions || []) {
      if (!checked.has(sug.company_name)) continue;
      try {
        await api.addPortfolioCompany(token, investorId, {
          company_name: sug.matched_startup?.name || sug.company_name,
          startup_id: sug.matched_startup?.id,
        });
      } catch {
        // Skip duplicates or errors
      }
    }
    setSaving(false);
    onClaimed();
  }

  function toggleCheck(name: string) {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  // Suggestion confirmation view
  if (suggestions) {
    return (
      <div className="rounded border border-accent/30 bg-accent/5 p-6 mb-10">
        <h3 className="font-serif text-lg text-text-primary mb-2">
          We found these investments — are these yours?
        </h3>
        <p className="text-sm text-text-secondary mb-4">
          Uncheck any that don&apos;t belong to you.
        </p>
        <div className="space-y-2 mb-4">
          {suggestions.map((sug) => (
            <label
              key={sug.company_name}
              className="flex items-center gap-3 rounded border border-border bg-surface p-3 cursor-pointer hover:border-text-tertiary transition"
            >
              <input
                type="checkbox"
                checked={checked.has(sug.company_name)}
                onChange={() => toggleCheck(sug.company_name)}
                className="accent-accent"
              />
              {sug.matched_startup?.logo_url ? (
                <img
                  src={sug.matched_startup.logo_url}
                  alt={sug.company_name}
                  className="h-8 w-8 rounded object-cover"
                />
              ) : (
                <div className="h-8 w-8 rounded bg-background border border-border flex items-center justify-center font-serif text-sm text-text-tertiary">
                  {sug.company_name[0]}
                </div>
              )}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-text-primary truncate">
                  {sug.matched_startup?.name || sug.company_name}
                </p>
                {sug.matched_startup?.stage && (
                  <p className="text-xs text-text-tertiary">
                    {stageLabels[sug.matched_startup.stage] || sug.matched_startup.stage}
                  </p>
                )}
              </div>
              {sug.matched_startup && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-score-high/10 text-score-high font-medium">
                  Matched
                </span>
              )}
            </label>
          ))}
        </div>
        <button
          onClick={handleConfirm}
          disabled={saving || checked.size === 0}
          className="px-6 py-2.5 bg-accent text-white text-sm font-medium rounded hover:bg-accent-hover disabled:opacity-50 transition"
        >
          {saving ? "Saving..." : `Confirm ${checked.size} Companies`}
        </button>
      </div>
    );
  }

  // Initial claim banner
  return (
    <div className="rounded border border-accent/30 bg-accent/5 p-4 mb-10 flex items-center justify-between">
      <div>
        <p className="text-sm font-medium text-text-primary">
          Is this you? Claim your profile to manage your portfolio.
        </p>
      </div>
      <button
        onClick={handleClaim}
        disabled={claiming}
        className="px-4 py-2 bg-accent text-white text-sm font-medium rounded hover:bg-accent-hover disabled:opacity-50 transition shrink-0"
      >
        {claiming ? "Claiming..." : "Claim Profile"}
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/score/\[id\]/claim-banner.tsx
git commit -m "feat: add claim banner component for investor profile"
```

---

### Task 5: Add Company Modal

**Files:**
- Create: `frontend/app/score/[id]/add-company-modal.tsx`

- [ ] **Step 1: Create the add company modal**

Create `frontend/app/score/[id]/add-company-modal.tsx`:

```tsx
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

const STAGES = [
  { value: "pre_seed", label: "Pre-Seed" },
  { value: "seed", label: "Seed" },
  { value: "series_a", label: "Series A" },
  { value: "series_b", label: "Series B" },
  { value: "series_c", label: "Series C" },
  { value: "growth", label: "Growth" },
];

interface StartupResult {
  id: string;
  slug: string;
  name: string;
  logo_url: string | null;
  stage: string;
  ai_score: number | null;
}

export function AddCompanyModal({
  open,
  onClose,
  token,
  investorId,
  onAdded,
  prefill,
}: {
  open: boolean;
  onClose: () => void;
  token: string;
  investorId: string;
  onAdded: () => void;
  prefill?: { startup_id: string; company_name: string };
}) {
  const overlayRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<StartupResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [selectedStartup, setSelectedStartup] = useState<StartupResult | null>(null);
  const [manualMode, setManualMode] = useState(false);

  // Form fields
  const [companyName, setCompanyName] = useState("");
  const [companyWebsite, setCompanyWebsite] = useState("");
  const [roundStage, setRoundStage] = useState("");
  const [investmentDate, setInvestmentDate] = useState("");
  const [checkSize, setCheckSize] = useState("");
  const [isLead, setIsLead] = useState(false);
  const [boardSeat, setBoardSeat] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // Prefill support (for startup page button)
  useEffect(() => {
    if (open && prefill) {
      setCompanyName(prefill.company_name);
      setSelectedStartup({ id: prefill.startup_id, name: prefill.company_name } as StartupResult);
      setManualMode(false);
    }
  }, [open, prefill]);

  // Reset on close
  useEffect(() => {
    if (!open) {
      setQuery("");
      setResults([]);
      setSelectedStartup(null);
      setManualMode(false);
      setCompanyName("");
      setCompanyWebsite("");
      setRoundStage("");
      setInvestmentDate("");
      setCheckSize("");
      setIsLead(false);
      setBoardSeat(false);
      setError("");
    }
  }, [open]);

  // Debounced search
  useEffect(() => {
    if (!query.trim() || query.length < 2) {
      setResults([]);
      return;
    }
    const timer = setTimeout(async () => {
      setSearching(true);
      try {
        const params = new URLSearchParams({ q: query, per_page: "5" });
        const res = await fetch(`${API_URL}/api/startups?${params}`);
        if (res.ok) {
          const data = await res.json();
          setResults(data.items || []);
        }
      } catch { /* ignore */ }
      setSearching(false);
    }, 300);
    return () => clearTimeout(timer);
  }, [query]);

  const handleKey = useCallback(
    (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); },
    [onClose]
  );

  useEffect(() => {
    if (open) document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [open, handleKey]);

  function selectStartup(s: StartupResult) {
    setSelectedStartup(s);
    setCompanyName(s.name);
    setQuery("");
    setResults([]);
  }

  async function handleSubmit() {
    if (!companyName.trim()) {
      setError("Company name is required");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await api.addPortfolioCompany(token, investorId, {
        company_name: companyName.trim(),
        startup_id: selectedStartup?.id,
        company_website: companyWebsite || undefined,
        investment_date: investmentDate || undefined,
        round_stage: roundStage || undefined,
        check_size: checkSize || undefined,
        is_lead: isLead,
        board_seat: boardSeat,
      });
      onAdded();
      onClose();
    } catch (e: any) {
      setError(e.message || "Failed to add company");
    }
    setSaving(false);
  }

  if (!open) return null;

  const stageLabel = STAGES.find((s) => s.value === (selectedStartup?.stage))?.label;

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-text-primary/30 backdrop-blur-sm"
      onClick={(e) => { if (e.target === overlayRef.current) onClose(); }}
    >
      <div className="bg-surface border border-border rounded p-6 w-full max-w-md mx-4 shadow-lg max-h-[90vh] overflow-y-auto">
        <h3 className="font-serif text-lg text-text-primary mb-4">Add Company to Portfolio</h3>

        {/* Search / Selected / Manual */}
        {!selectedStartup && !manualMode && !prefill && (
          <div className="mb-4">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search companies..."
              className="w-full px-3 py-2 text-sm rounded border border-border bg-background text-text-primary placeholder-text-tertiary focus:outline-none focus:border-accent"
            />
            {searching && <p className="text-xs text-text-tertiary mt-1">Searching...</p>}
            {results.length > 0 && (
              <div className="mt-1 border border-border rounded bg-surface divide-y divide-border">
                {results.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => selectStartup(s)}
                    className="w-full text-left px-3 py-2 flex items-center gap-3 hover:bg-hover-row transition"
                  >
                    {s.logo_url ? (
                      <img src={s.logo_url} alt={s.name} className="h-7 w-7 rounded object-cover" />
                    ) : (
                      <div className="h-7 w-7 rounded bg-background border border-border flex items-center justify-center font-serif text-xs text-text-tertiary">
                        {s.name[0]}
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-text-primary truncate">{s.name}</p>
                    </div>
                    {s.ai_score != null && (
                      <span className="text-xs tabular-nums text-text-tertiary">AI: {s.ai_score.toFixed(0)}</span>
                    )}
                  </button>
                ))}
              </div>
            )}
            <button
              onClick={() => setManualMode(true)}
              className="text-xs text-accent hover:text-accent-hover mt-2 transition"
            >
              Company not listed? Add manually
            </button>
          </div>
        )}

        {/* Selected startup chip */}
        {selectedStartup && (
          <div className="flex items-center gap-2 mb-4 rounded border border-score-high/30 bg-score-high/5 px-3 py-2">
            <span className="text-sm text-text-primary flex-1 truncate">{selectedStartup.name}</span>
            {stageLabel && <span className="text-xs text-text-tertiary">{stageLabel}</span>}
            {!prefill && (
              <button
                onClick={() => { setSelectedStartup(null); setCompanyName(""); }}
                className="text-xs text-text-tertiary hover:text-text-primary"
              >
                &times;
              </button>
            )}
          </div>
        )}

        {/* Manual entry fields */}
        {manualMode && !selectedStartup && (
          <div className="space-y-3 mb-4">
            <input
              type="text"
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              placeholder="Company name *"
              className="w-full px-3 py-2 text-sm rounded border border-border bg-background text-text-primary placeholder-text-tertiary focus:outline-none focus:border-accent"
            />
            <input
              type="url"
              value={companyWebsite}
              onChange={(e) => setCompanyWebsite(e.target.value)}
              placeholder="Website (optional)"
              className="w-full px-3 py-2 text-sm rounded border border-border bg-background text-text-primary placeholder-text-tertiary focus:outline-none focus:border-accent"
            />
          </div>
        )}

        {/* Investment detail form */}
        {(selectedStartup || manualMode) && (
          <div className="space-y-3 mb-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-text-tertiary mb-1 block">Round</label>
                <select
                  value={roundStage}
                  onChange={(e) => setRoundStage(e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded border border-border bg-background text-text-primary focus:outline-none focus:border-accent"
                >
                  <option value="">Select...</option>
                  {STAGES.map((s) => (
                    <option key={s.value} value={s.value}>{s.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-xs text-text-tertiary mb-1 block">Date</label>
                <input
                  type="date"
                  value={investmentDate}
                  onChange={(e) => setInvestmentDate(e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded border border-border bg-background text-text-primary focus:outline-none focus:border-accent"
                />
              </div>
            </div>
            <div>
              <label className="text-xs text-text-tertiary mb-1 block">Check Size</label>
              <input
                type="text"
                value={checkSize}
                onChange={(e) => setCheckSize(e.target.value)}
                placeholder="e.g. $150K"
                className="w-full px-3 py-2 text-sm rounded border border-border bg-background text-text-primary placeholder-text-tertiary focus:outline-none focus:border-accent"
              />
            </div>
            <div className="flex items-center gap-6">
              <label className="flex items-center gap-2 text-sm text-text-secondary cursor-pointer">
                <input
                  type="checkbox"
                  checked={isLead}
                  onChange={(e) => setIsLead(e.target.checked)}
                  className="accent-accent"
                />
                Lead investor
              </label>
              <label className="flex items-center gap-2 text-sm text-text-secondary cursor-pointer">
                <input
                  type="checkbox"
                  checked={boardSeat}
                  onChange={(e) => setBoardSeat(e.target.checked)}
                  className="accent-accent"
                />
                Board seat
              </label>
            </div>
          </div>
        )}

        {error && <p className="text-xs text-score-low mb-3">{error}</p>}

        <div className="flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm rounded border border-border text-text-secondary hover:text-text-primary hover:border-text-tertiary transition"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={saving || (!companyName.trim())}
            className="px-4 py-2 text-sm font-medium rounded bg-accent text-white hover:bg-accent-hover disabled:opacity-50 transition"
          >
            {saving ? "Adding..." : "Add to Portfolio"}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/score/\[id\]/add-company-modal.tsx
git commit -m "feat: add company modal with type-ahead search"
```

---

### Task 6: Portfolio Section Component

**Files:**
- Create: `frontend/app/score/[id]/portfolio-section.tsx`

- [ ] **Step 1: Create the portfolio section component**

Create `frontend/app/score/[id]/portfolio-section.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { AddCompanyModal } from "./add-company-modal";
import { ConfirmModal } from "@/components/Modal";

const stageLabels: Record<string, string> = {
  pre_seed: "Pre-Seed", seed: "Seed", series_a: "Series A",
  series_b: "Series B", series_c: "Series C", growth: "Growth",
  public: "Public",
};

const statusStyles: Record<string, string> = {
  active: "border-score-high/30 text-score-high",
  exited: "border-accent/30 text-accent",
  written_off: "border-score-low/30 text-score-low",
};

interface PortfolioItem {
  id: string;
  investor_id: string;
  startup_id: string | null;
  company_name: string;
  company_website: string | null;
  investment_date: string | null;
  round_stage: string | null;
  check_size: string | null;
  is_lead: boolean;
  board_seat: boolean;
  status: string;
  exit_type: string | null;
  exit_multiple: number | null;
  is_public: boolean;
  startup_slug: string | null;
  startup_logo_url: string | null;
  startup_stage: string | null;
}

export function PortfolioSection({
  investorId,
  token,
}: {
  investorId: string;
  token: string | null;
}) {
  const [items, setItems] = useState<PortfolioItem[]>([]);
  const [isOwner, setIsOwner] = useState(false);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [menuOpen, setMenuOpen] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<PortfolioItem | null>(null);

  async function loadPortfolio() {
    try {
      const data = await api.getPortfolio(token || "", investorId);
      setItems(data.items);
      setIsOwner(data.is_owner);
    } catch { /* ignore */ }
    setLoading(false);
  }

  useEffect(() => {
    loadPortfolio();
  }, [investorId, token]);

  async function handleDelete() {
    if (!deleteTarget || !token) return;
    try {
      await api.deletePortfolioCompany(token, investorId, deleteTarget.id);
      setItems((prev) => prev.filter((i) => i.id !== deleteTarget.id));
    } catch { /* ignore */ }
    setDeleteTarget(null);
  }

  async function togglePublic(item: PortfolioItem) {
    if (!token) return;
    try {
      await api.updatePortfolioCompany(token, investorId, item.id, {
        is_public: !item.is_public,
      });
      setItems((prev) =>
        prev.map((i) => (i.id === item.id ? { ...i, is_public: !i.is_public } : i))
      );
    } catch { /* ignore */ }
    setMenuOpen(null);
  }

  if (loading) return null;
  if (!isOwner && items.length === 0) return null;

  // Summary stats
  const exitCount = items.filter((i) => i.status === "exited").length;
  const stageCounts: Record<string, number> = {};
  for (const item of items) {
    const s = item.round_stage || "unknown";
    stageCounts[s] = (stageCounts[s] || 0) + 1;
  }
  const topStage = Object.entries(stageCounts).sort((a, b) => b[1] - a[1])[0];

  return (
    <section id="portfolio" className="mb-10 scroll-mt-20">
      <div className="flex items-center justify-between mb-6">
        <h2 className="font-serif text-xl text-text-primary">Portfolio</h2>
        {isOwner && (
          <button
            onClick={() => setShowModal(true)}
            className="px-4 py-2 text-sm font-medium rounded bg-accent text-white hover:bg-accent-hover transition"
          >
            + Add Company
          </button>
        )}
      </div>

      {/* Summary bar (owner only) */}
      {isOwner && items.length > 0 && (
        <p className="text-sm text-text-secondary mb-4">
          {items.length} {items.length === 1 ? "company" : "companies"}
          {exitCount > 0 && ` · ${exitCount} ${exitCount === 1 ? "exit" : "exits"}`}
          {topStage && topStage[0] !== "unknown" && ` · ${stageLabels[topStage[0]] || topStage[0]} focus`}
        </p>
      )}

      {items.length === 0 && isOwner && (
        <div className="rounded border border-border bg-surface p-8 text-center">
          <p className="text-sm text-text-tertiary mb-3">No portfolio companies yet.</p>
          <button
            onClick={() => setShowModal(true)}
            className="text-sm text-accent hover:text-accent-hover transition"
          >
            Add your first company
          </button>
        </div>
      )}

      {/* Portfolio grid */}
      {items.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {items.map((item) => (
            <div
              key={item.id}
              className={`relative rounded border border-border bg-surface p-4 hover:border-text-tertiary transition ${
                isOwner && !item.is_public ? "opacity-60" : ""
              }`}
            >
              {/* Menu button (owner only) */}
              {isOwner && (
                <div className="absolute top-3 right-3">
                  <button
                    onClick={() => setMenuOpen(menuOpen === item.id ? null : item.id)}
                    className="text-text-tertiary hover:text-text-primary text-sm px-1"
                  >
                    &middot;&middot;&middot;
                  </button>
                  {menuOpen === item.id && (
                    <div className="absolute right-0 top-6 bg-surface border border-border rounded shadow-lg z-10 py-1 w-40">
                      <button
                        onClick={() => togglePublic(item)}
                        className="w-full text-left px-3 py-1.5 text-xs text-text-secondary hover:bg-hover-row transition"
                      >
                        {item.is_public ? "Make Private" : "Make Public"}
                      </button>
                      <button
                        onClick={() => { setDeleteTarget(item); setMenuOpen(null); }}
                        className="w-full text-left px-3 py-1.5 text-xs text-score-low hover:bg-hover-row transition"
                      >
                        Remove
                      </button>
                    </div>
                  )}
                </div>
              )}

              <div className="flex items-center gap-3 mb-3">
                {item.startup_logo_url ? (
                  <img src={item.startup_logo_url} alt={item.company_name} className="h-9 w-9 rounded object-cover" />
                ) : (
                  <div className="h-9 w-9 rounded bg-background border border-border flex items-center justify-center font-serif text-sm text-text-tertiary">
                    {item.company_name[0]}
                  </div>
                )}
                <div className="min-w-0 flex-1 pr-6">
                  {item.startup_slug ? (
                    <Link
                      href={`/startups/${item.startup_slug}`}
                      className="text-sm font-medium text-text-primary truncate block hover:text-accent transition"
                    >
                      {item.company_name}
                    </Link>
                  ) : (
                    <p className="text-sm font-medium text-text-primary truncate">{item.company_name}</p>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-2 flex-wrap">
                {item.round_stage && (
                  <span className="text-xs px-2 py-0.5 rounded border border-border text-text-tertiary">
                    {stageLabels[item.round_stage] || item.round_stage}
                  </span>
                )}
                <span className={`text-xs px-2 py-0.5 rounded border ${statusStyles[item.status] || "border-border text-text-tertiary"}`}>
                  {item.status === "written_off" ? "Written Off" : item.status.charAt(0).toUpperCase() + item.status.slice(1)}
                </span>
                {item.is_lead && (
                  <span className="text-xs px-2 py-0.5 rounded border border-accent/30 text-accent">
                    Lead
                  </span>
                )}
                {isOwner && !item.is_public && (
                  <span className="text-xs text-text-tertiary">Private</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {isOwner && (
        <AddCompanyModal
          open={showModal}
          onClose={() => setShowModal(false)}
          token={token!}
          investorId={investorId}
          onAdded={loadPortfolio}
        />
      )}

      <ConfirmModal
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        title="Remove Company"
        message={`Remove ${deleteTarget?.company_name} from your portfolio?`}
        confirmLabel="Remove"
      />
    </section>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/score/\[id\]/portfolio-section.tsx
git commit -m "feat: add portfolio section with grid, menu, and delete"
```

---

### Task 7: Wire Portfolio + Claim into Score Page

**Files:**
- Modify: `frontend/app/score/[id]/page.tsx:1-255`

- [ ] **Step 1: Update the score page to include claim banner and portfolio section**

In `frontend/app/score/[id]/page.tsx`, add the imports at the top (after the existing imports on lines 1-4):

```tsx
import { ClaimBanner } from "./claim-banner";
import { PortfolioSection } from "./portfolio-section";
```

Add state for claim flow inside `ScoreDetailPage()`, after the existing state declarations (after line 44):

```tsx
  const [showClaimBanner, setShowClaimBanner] = useState(false);
  const [claimDismissed, setClaimDismissed] = useState(false);
```

Add a check inside the `useEffect` that fetches ranking data. After `setData(result)` on line 75, add logic to determine whether to show the claim banner. Replace the fetchRanking function body inside the try block (lines 57-75) with:

```tsx
        const res = await fetch(`${API_URL}/api/investors/${id}/ranking`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.status === 403) {
          const meRes = await fetch(`${API_URL}/api/investors/me/ranking`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (meRes.ok) {
            const meData = await meRes.json();
            router.replace(`/score/${meData.investor_id}`);
            return;
          }
          throw new Error("no_access");
        }
        if (!res.ok) throw new Error("Failed to load score data");
        const result = await res.json();
        setData(result);

        // Check if this investor profile can be claimed by current user
        const portfolioRes = await fetch(`${API_URL}/api/investors/${id}/portfolio`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (portfolioRes.ok) {
          const portfolioData = await portfolioRes.json();
          if (!portfolioData.is_owner) {
            setShowClaimBanner(true);
          }
        }
```

Then in the JSX, after the narrative section (after line 251's closing `</div>` for the narrative), add:

```tsx
      {/* Claim Banner */}
      {showClaimBanner && !claimDismissed && (
        <ClaimBanner
          investorId={id}
          token={(session as any)?.backendToken}
          onClaimed={() => {
            setClaimDismissed(true);
            setShowClaimBanner(false);
          }}
        />
      )}

      {/* Portfolio */}
      <PortfolioSection
        investorId={id}
        token={(session as any)?.backendToken}
      />
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/score/\[id\]/page.tsx
git commit -m "feat: wire claim banner and portfolio section into score page"
```

---

### Task 8: "Add to Portfolio" Button on Startup Pages

**Files:**
- Create: `frontend/app/startups/[slug]/portfolio-button.tsx`
- Modify: `frontend/app/startups/[slug]/page.tsx:166-167`

- [ ] **Step 1: Create the portfolio button component**

Create `frontend/app/startups/[slug]/portfolio-button.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { api } from "@/lib/api";
import { AddCompanyModal } from "@/app/score/[id]/add-company-modal";

export function PortfolioButton({
  startupId,
  startupName,
}: {
  startupId: string;
  startupName: string;
}) {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;
  const role = (session as any)?.role;
  const [investorId, setInvestorId] = useState<string | null>(null);
  const [inPortfolio, setInPortfolio] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!token || role !== "investor") return;

    // Get investor profile for this user
    fetch(`${process.env.NEXT_PUBLIC_API_URL || ""}/api/investors/me/ranking`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => {
        if (!res.ok) throw new Error("Not an investor");
        return res.json();
      })
      .then((data) => {
        setInvestorId(data.investor_id);
        // Check if startup is already in portfolio
        return api.getPortfolio(token, data.investor_id);
      })
      .then((portfolio) => {
        const found = portfolio.items.some(
          (item) => item.startup_id === startupId
        );
        setInPortfolio(found);
        setReady(true);
      })
      .catch(() => setReady(true));
  }, [token, role, startupId]);

  if (!token || role !== "investor" || !ready || !investorId) return null;

  if (inPortfolio) {
    return (
      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded border border-score-high/30 text-xs font-medium text-score-high bg-score-high/5">
        <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M20 6L9 17l-5-5" />
        </svg>
        In Portfolio
      </span>
    );
  }

  return (
    <>
      <button
        onClick={() => setShowModal(true)}
        className="inline-flex items-center gap-1.5 px-3 py-1 rounded border border-border text-xs font-medium text-text-secondary hover:border-accent/50 hover:text-accent transition"
      >
        <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 5v14M5 12h14" />
        </svg>
        Add to Portfolio
      </button>
      <AddCompanyModal
        open={showModal}
        onClose={() => setShowModal(false)}
        token={token}
        investorId={investorId}
        onAdded={() => setInPortfolio(true)}
        prefill={{ startup_id: startupId, company_name: startupName }}
      />
    </>
  );
}
```

- [ ] **Step 2: Add the PortfolioButton to the startup detail page**

In `frontend/app/startups/[slug]/page.tsx`, add the import at the top (after line 7):

```tsx
import { PortfolioButton } from "./portfolio-button";
```

Then in the JSX, add the button next to WatchButton. Find the line with `<WatchButton startupId={startup.id} />` (line 167) and add after it:

```tsx
            <PortfolioButton startupId={startup.id} startupName={startup.name} />
```

- [ ] **Step 3: Commit**

```bash
git add frontend/app/startups/\[slug\]/portfolio-button.tsx frontend/app/startups/\[slug\]/page.tsx
git commit -m "feat: add 'Add to Portfolio' button on startup detail pages"
```

---

### Task 9: Add Portfolio Link to Navbar

**Files:**
- Modify: `frontend/components/Navbar.tsx:1-126`

- [ ] **Step 1: Add Portfolio nav link for investor users**

In `frontend/components/Navbar.tsx`, find the section where the score pill is rendered (around line 84-92). Add a "Portfolio" link before the score pill. Replace lines 84-92 with:

```tsx
            {score && (
              <Link
                href={`/score/${score.investor_id}#portfolio`}
                className="hidden md:flex text-sm text-text-secondary hover:text-text-primary transition"
              >
                Portfolio
              </Link>
            )}
            {score && (
              <Link
                href={`/score/${score.investor_id}`}
                className={`hidden md:flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium transition hover:opacity-80 ${scorePillClasses(score.overall_score)}`}
              >
                <span>Score</span>
                <span className="tabular-nums">{Math.round(score.overall_score)}</span>
              </Link>
            )}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/Navbar.tsx
git commit -m "feat: add Portfolio link in navbar for investor users"
```

---

### Task 10: Deploy and Verify

**Files:** None (deployment task)

- [ ] **Step 1: Run the SQL migration on production**

```bash
ssh -i ~/.ssh/deepthesis-deploy.pem ec2-user@3.212.120.144 "docker compose -f /home/ec2-user/acutal/docker-compose.prod.yml exec -T db psql -U postgres -d deepthesis -c \"
ALTER TABLE investors ADD COLUMN IF NOT EXISTS user_id UUID UNIQUE REFERENCES users(id) ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS portfolio_companies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investor_id UUID NOT NULL REFERENCES investors(id) ON DELETE CASCADE,
    startup_id UUID REFERENCES startups(id) ON DELETE SET NULL,
    company_name VARCHAR(300) NOT NULL,
    company_website VARCHAR(500),
    investment_date DATE,
    round_stage VARCHAR(50),
    check_size VARCHAR(100),
    is_lead BOOLEAN NOT NULL DEFAULT false,
    board_seat BOOLEAN NOT NULL DEFAULT false,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    exit_type VARCHAR(20),
    exit_multiple FLOAT,
    is_public BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_portfolio_investor_company UNIQUE (investor_id, company_name)
);

CREATE INDEX IF NOT EXISTS ix_portfolio_companies_investor_id ON portfolio_companies(investor_id);
CREATE INDEX IF NOT EXISTS ix_portfolio_companies_startup_id ON portfolio_companies(startup_id);
\""
```

- [ ] **Step 2: Deploy backend**

```bash
rsync -az -e "ssh -i ~/.ssh/deepthesis-deploy.pem" /Users/leemosbacker/acutal/backend/ ec2-user@3.212.120.144:/home/ec2-user/acutal/backend/
ssh -i ~/.ssh/deepthesis-deploy.pem ec2-user@3.212.120.144 "cd /home/ec2-user/acutal && docker compose -f docker-compose.prod.yml --env-file .env up -d --build backend"
```

- [ ] **Step 3: Deploy frontend**

```bash
rsync -az -e "ssh -i ~/.ssh/deepthesis-deploy.pem" /Users/leemosbacker/acutal/frontend/ ec2-user@3.212.120.144:/home/ec2-user/acutal/frontend/ --exclude node_modules --exclude .next
ssh -i ~/.ssh/deepthesis-deploy.pem ec2-user@3.212.120.144 "cd /home/ec2-user/acutal && docker compose -f docker-compose.prod.yml --env-file .env up -d --build frontend"
```

- [ ] **Step 4: Verify endpoints**

```bash
# Test portfolio list (should return empty items)
curl -s http://localhost:8000/api/investors/<test-investor-id>/portfolio | python3 -m json.tool

# Test claim endpoint (should return 401 without auth)
curl -s -X POST http://localhost:8000/api/investors/claim
```

- [ ] **Step 5: Commit all remaining changes**

```bash
git add -A
git commit -m "feat: investor portfolio management — Phase 1 complete"
```
