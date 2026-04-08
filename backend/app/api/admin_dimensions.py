import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_role
from app.db.session import get_db
from app.models.dimension import StartupDimension
from app.models.startup import Startup
from app.models.template import DueDiligenceTemplate
from app.models.user import User
from app.utils import slugify

router = APIRouter()


class ApplyTemplateIn(BaseModel):
    template_id: str


class DimensionIn(BaseModel):
    dimension_name: str
    weight: float = 1.0
    sort_order: int = 0


class UpdateDimensionsIn(BaseModel):
    dimensions: list[DimensionIn]


def _serialize_dimension(d: StartupDimension) -> dict:
    return {
        "id": str(d.id),
        "dimension_name": d.dimension_name,
        "dimension_slug": d.dimension_slug,
        "weight": d.weight,
        "sort_order": d.sort_order,
    }


@router.post("/api/admin/startups/{startup_id}/apply-template")
async def apply_template(
    startup_id: uuid.UUID,
    body: ApplyTemplateIn,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    # Verify startup exists
    result = await db.execute(select(Startup).where(Startup.id == startup_id))
    startup = result.scalar_one_or_none()
    if startup is None:
        raise HTTPException(status_code=404, detail="Startup not found")

    # Verify template exists and load dimensions
    template_uuid = uuid.UUID(body.template_id)
    result = await db.execute(
        select(DueDiligenceTemplate)
        .options(selectinload(DueDiligenceTemplate.dimensions))
        .where(DueDiligenceTemplate.id == template_uuid)
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    # Delete existing dimensions
    await db.execute(
        delete(StartupDimension).where(StartupDimension.startup_id == startup_id)
    )
    await db.flush()

    # Copy dimensions from template
    new_dims = []
    for td in sorted(template.dimensions, key=lambda d: d.sort_order):
        dim = StartupDimension(
            startup_id=startup_id,
            dimension_name=td.dimension_name,
            dimension_slug=td.dimension_slug,
            weight=td.weight,
            sort_order=td.sort_order,
        )
        db.add(dim)
        new_dims.append(dim)

    # Set template_id on startup
    startup.template_id = template_uuid
    await db.commit()

    # Refresh to get generated IDs
    for dim in new_dims:
        await db.refresh(dim)

    return {
        "template_id": str(template_uuid),
        "dimensions": [_serialize_dimension(d) for d in new_dims],
    }


@router.get("/api/admin/startups/{startup_id}/dimensions")
async def get_dimensions(
    startup_id: uuid.UUID,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StartupDimension)
        .where(StartupDimension.startup_id == startup_id)
        .order_by(StartupDimension.sort_order)
    )
    dims = result.scalars().all()
    return [_serialize_dimension(d) for d in dims]


@router.put("/api/admin/startups/{startup_id}/dimensions")
async def update_dimensions(
    startup_id: uuid.UUID,
    body: UpdateDimensionsIn,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    # Delete existing dimensions
    await db.execute(
        delete(StartupDimension).where(StartupDimension.startup_id == startup_id)
    )
    await db.flush()

    # Create new dimensions
    new_dims = []
    for dim_in in body.dimensions:
        dim = StartupDimension(
            startup_id=startup_id,
            dimension_name=dim_in.dimension_name,
            dimension_slug=slugify(dim_in.dimension_name),
            weight=dim_in.weight,
            sort_order=dim_in.sort_order,
        )
        db.add(dim)
        new_dims.append(dim)

    await db.commit()

    for dim in new_dims:
        await db.refresh(dim)

    return [_serialize_dimension(d) for d in sorted(new_dims, key=lambda d: d.sort_order)]
