from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.db.session import get_db
from app.models.user import User

router = APIRouter()


@router.get("/api/admin/users")
async def list_users(
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User))
    users = result.scalars().all()
    return [
        {
            "id": str(u.id),
            "email": u.email,
            "name": u.name,
            "role": u.role.value,
        }
        for u in users
    ]
