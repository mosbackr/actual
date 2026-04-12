import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_role
from app.db.session import get_db
from app.models.startup import Startup
from app.models.template import DueDiligenceTemplate, TemplateDimension
from app.models.user import User
from app.utils import slugify

router = APIRouter()


class DimensionIn(BaseModel):
    dimension_name: str
    weight: float = 1.0
    sort_order: int = 0


class TemplateCreateIn(BaseModel):
    name: str
    description: str | None = None
    industry_slug: str | None = None
    stage: str | None = None
    dimensions: list[DimensionIn] = []


class TemplateUpdateIn(BaseModel):
    name: str
    description: str | None = None
    industry_slug: str | None = None
    stage: str | None = None
    dimensions: list[DimensionIn] = []


def _serialize_template(t: DueDiligenceTemplate) -> dict:
    return {
        "id": str(t.id),
        "name": t.name,
        "slug": t.slug,
        "description": t.description,
        "industry_slug": t.industry_slug,
        "stage": t.stage,
        "created_at": t.created_at.isoformat(),
        "dimensions": [
            {
                "id": str(d.id),
                "dimension_name": d.dimension_name,
                "dimension_slug": d.dimension_slug,
                "weight": d.weight,
                "sort_order": d.sort_order,
            }
            for d in sorted(t.dimensions, key=lambda d: d.sort_order)
        ],
    }


@router.get("/api/admin/dd-templates")
async def list_templates(
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DueDiligenceTemplate)
        .options(selectinload(DueDiligenceTemplate.dimensions))
        .order_by(DueDiligenceTemplate.name)
    )
    templates = result.scalars().all()
    return [_serialize_template(t) for t in templates]


@router.post("/api/admin/dd-templates", status_code=201)
async def create_template(
    body: TemplateCreateIn,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    template = DueDiligenceTemplate(
        name=body.name,
        slug=slugify(body.name),
        description=body.description,
        industry_slug=body.industry_slug,
        stage=body.stage,
    )
    db.add(template)
    await db.flush()

    for dim in body.dimensions:
        db.add(TemplateDimension(
            template_id=template.id,
            dimension_name=dim.dimension_name,
            dimension_slug=slugify(dim.dimension_name),
            weight=dim.weight,
            sort_order=dim.sort_order,
        ))

    await db.commit()
    result = await db.execute(
        select(DueDiligenceTemplate)
        .options(selectinload(DueDiligenceTemplate.dimensions))
        .where(DueDiligenceTemplate.id == template.id)
    )
    template = result.scalar_one()
    return _serialize_template(template)


@router.get("/api/admin/dd-templates/{template_id}")
async def get_template(
    template_id: uuid.UUID,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DueDiligenceTemplate)
        .options(selectinload(DueDiligenceTemplate.dimensions))
        .where(DueDiligenceTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return _serialize_template(template)


@router.put("/api/admin/dd-templates/{template_id}")
async def update_template(
    template_id: uuid.UUID,
    body: TemplateUpdateIn,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DueDiligenceTemplate)
        .options(selectinload(DueDiligenceTemplate.dimensions))
        .where(DueDiligenceTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    template.name = body.name
    template.slug = slugify(body.name)
    template.description = body.description
    template.industry_slug = body.industry_slug
    template.stage = body.stage

    await db.execute(
        delete(TemplateDimension).where(TemplateDimension.template_id == template_id)
    )
    await db.flush()

    for dim in body.dimensions:
        db.add(TemplateDimension(
            template_id=template.id,
            dimension_name=dim.dimension_name,
            dimension_slug=slugify(dim.dimension_name),
            weight=dim.weight,
            sort_order=dim.sort_order,
        ))

    await db.commit()
    db.expire_all()
    result = await db.execute(
        select(DueDiligenceTemplate)
        .options(selectinload(DueDiligenceTemplate.dimensions))
        .where(DueDiligenceTemplate.id == template_id)
    )
    template = result.scalar_one()
    return _serialize_template(template)


@router.delete("/api/admin/dd-templates/{template_id}", status_code=204)
async def delete_template(
    template_id: uuid.UUID,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DueDiligenceTemplate)
        .where(DueDiligenceTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    startup_result = await db.execute(
        select(Startup).where(Startup.template_id == template_id).limit(1)
    )
    if startup_result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Template is in use by one or more startups")

    await db.delete(template)
    await db.commit()
    return Response(status_code=204)
