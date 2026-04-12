import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from jose import jwt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db
from app.models.user import AuthProvider, User, UserRole

router = APIRouter()


class AdminLoginIn(BaseModel):
    email: str
    password: str


class AdminRegisterIn(BaseModel):
    email: str
    password: str
    name: str
    setup_key: str


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


@router.post("/api/admin/login")
async def admin_login(body: AdminLoginIn, db: AsyncSession = Depends(get_db)):
    """Authenticate admin user with email and password."""
    result = await db.execute(
        select(User).where(User.email == body.email, User.role == UserRole.superadmin)
    )
    user = result.scalar_one_or_none()

    if user is None or user.password_hash is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

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


@router.post("/api/admin/setup")
async def admin_setup(body: AdminRegisterIn, db: AsyncSession = Depends(get_db)):
    """Create the initial superadmin account.

    Requires ACUTAL_ADMIN_SETUP_KEY to prevent unauthorized creation.
    Only works when no superadmin exists yet, or with the correct setup key.
    """
    if body.setup_key != settings.admin_setup_key:
        raise HTTPException(status_code=403, detail="Invalid setup key")

    existing = await db.execute(
        select(User).where(User.email == body.email)
    )
    user = existing.scalar_one_or_none()

    if user is not None:
        # Upgrade existing user to superadmin with password
        user.role = UserRole.superadmin
        user.password_hash = hash_password(body.password)
        user.name = body.name
    else:
        user = User(
            email=body.email,
            name=body.name,
            auth_provider=AuthProvider.credentials,
            provider_id="credentials",
            role=UserRole.superadmin,
            password_hash=hash_password(body.password),
        )
        db.add(user)

    await db.commit()
    await db.refresh(user)

    return {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "role": user.role.value,
        },
    }
