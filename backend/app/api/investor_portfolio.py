import re
import uuid
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_user_or_none
from app.db.session import get_db
from app.models.investor import Investor
from app.models.portfolio import PortfolioCompany
from app.models.startup import EntityType, Startup, StartupStage, StartupStatus
from app.models.user import User, UserRole
from app.services.enrichment import run_enrichment_pipeline

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


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[-\s]+", "-", slug)
    return slug


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
    user: User | None = Depends(get_current_user_or_none),
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
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_investor_and_check_owner(investor_id, user, db)

    # Validate startup_id if provided, or auto-match by name
    startup_id_val = None
    if body.startup_id:
        try:
            sid = uuid.UUID(body.startup_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid startup_id")
        startup = await db.get(Startup, sid)
        if not startup:
            raise HTTPException(status_code=400, detail="Startup not found")
        startup_id_val = startup.id
    else:
        # Try to auto-match company name against existing startups
        result = await db.execute(
            select(Startup)
            .where(Startup.name.ilike(body.company_name.strip()))
            .limit(1)
        )
        matched = result.scalar_one_or_none()
        if matched:
            startup_id_val = matched.id
        else:
            # Create a new startup record and trigger enrichment
            name = body.company_name.strip()
            slug = _slugify(name)
            existing_slug = await db.execute(
                select(Startup).where(Startup.slug == slug)
            )
            if existing_slug.scalar_one_or_none() is not None:
                slug = f"{slug}-{uuid.uuid4().hex[:6]}"
            new_startup = Startup(
                name=name,
                slug=slug,
                description=f"{name} — added via investor portfolio",
                website_url=body.company_website or None,
                stage=StartupStage.seed,
                status=StartupStatus.approved,
                entity_type=EntityType.startup,
            )
            db.add(new_startup)
            await db.flush()
            startup_id_val = new_startup.id
            background_tasks.add_task(run_enrichment_pipeline, str(new_startup.id))

    # Check for duplicate by name
    existing = await db.execute(
        select(PortfolioCompany).where(
            PortfolioCompany.investor_id == investor_id,
            PortfolioCompany.company_name == body.company_name,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Company already in portfolio")

    # Also check for duplicate by startup_id (different name, same company)
    if startup_id_val:
        existing_by_startup = await db.execute(
            select(PortfolioCompany).where(
                PortfolioCompany.investor_id == investor_id,
                PortfolioCompany.startup_id == startup_id_val,
            )
        )
        if existing_by_startup.scalar_one_or_none():
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

    if "startup_id" in update_data:
        sid_str = update_data["startup_id"]
        if sid_str:
            try:
                sid = uuid.UUID(sid_str)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid startup_id")
            startup = await db.get(Startup, sid)
            if not startup:
                raise HTTPException(status_code=400, detail="Startup not found")
            update_data["startup_id"] = startup.id
        else:
            update_data["startup_id"] = None

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
            Investor.email.ilike(user.email),
        )
    )
    investor = result.scalar_one_or_none()
    if not investor:
        raise HTTPException(status_code=404, detail="No investor profile matches your email")
    if investor.user_id is not None:
        raise HTTPException(status_code=409, detail="This investor profile has already been claimed")

    investor.user_id = user.id
    if user.role == UserRole.user:
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


# ── Update Investor Profile ───────────────────��───────────────────────────

class InvestorProfileUpdateBody(BaseModel):
    firm_name: str | None = None
    partner_name: str | None = None
    title: str | None = None
    website: str | None = None
    location: str | None = None
    stage_focus: str | None = None
    sector_focus: str | None = None


@router.put("/api/investors/{investor_id}/profile")
async def update_investor_profile(
    investor_id: uuid.UUID,
    body: InvestorProfileUpdateBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    investor = await _get_investor_and_check_owner(investor_id, user, db)
    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(investor, key, value)
    await db.commit()
    await db.refresh(investor)
    return {
        "id": str(investor.id),
        "firm_name": investor.firm_name,
        "partner_name": investor.partner_name,
        "title": investor.title,
        "website": investor.website,
        "location": investor.location,
        "stage_focus": investor.stage_focus,
        "sector_focus": investor.sector_focus,
    }


# ── Rescore Investor ──────────────────────────────────────────────────────

async def _run_rescore(investor_id: str) -> None:
    """Background task: re-run investor ranking pipeline."""
    from app.services.investor_ranking import _score_single_investor
    from app.db.session import async_session

    async with async_session() as db:
        investor = await db.get(Investor, uuid.UUID(investor_id))
        if not investor:
            return
        await _score_single_investor(db, investor)


@router.post("/api/investors/{investor_id}/rescore")
async def rescore_investor(
    investor_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_investor_and_check_owner(investor_id, user, db)
    background_tasks.add_task(_run_rescore, str(investor_id))
    return {"status": "rescoring"}
