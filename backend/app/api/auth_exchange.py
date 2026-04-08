from fastapi import APIRouter, Depends
from jose import jwt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db
from app.models.user import AuthProvider, User

router = APIRouter()


class TokenExchangeIn(BaseModel):
    email: str
    name: str
    provider: str
    provider_id: str


@router.post("/api/auth/token")
async def exchange_token(body: TokenExchangeIn, db: AsyncSession = Depends(get_db)):
    """Exchange OAuth credentials for a backend JWT.
    Called by NextAuth after successful OAuth authentication.
    Creates the user record on first login."""
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            email=body.email,
            name=body.name,
            auth_provider=AuthProvider(body.provider),
            provider_id=body.provider_id,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    token = jwt.encode(
        {"sub": str(user.id), "email": user.email, "role": user.role.value},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    return {
        "token": token,
        "user": {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "role": user.role.value,
        },
    }
