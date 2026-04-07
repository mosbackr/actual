from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.industry import Industry
from app.models.skill import Skill

router = APIRouter()


@router.get("/api/industries")
async def list_industries(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Industry).order_by(Industry.name))
    industries = result.scalars().all()
    return [{"id": str(i.id), "name": i.name, "slug": i.slug} for i in industries]


@router.get("/api/skills")
async def list_skills(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Skill).order_by(Skill.name))
    skills = result.scalars().all()
    return [{"id": str(s.id), "name": s.name, "slug": s.slug} for s in skills]
