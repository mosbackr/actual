import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from jose import jwt
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db
from app.api.deps import get_current_user
from app.models.investor import Investor
from app.models.user import AuthProvider, SubscriptionStatus, SubscriptionTier, User, UserRole
from app.services import email_service


router = APIRouter()


class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    name: str
    ecosystem_role: str | None = None
    region: str | None = None
    promo_code: str | None = None


class LoginIn(BaseModel):
    email: str
    password: str


class ProfileUpdateIn(BaseModel):
    name: str | None = None
    avatar_url: str | None = None
    ecosystem_role: str | None = None
    region: str | None = None


def _user_dict(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "role": user.role.value,
        "avatar_url": user.avatar_url,
        "ecosystem_role": user.ecosystem_role,
        "region": user.region,
    }


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


async def _maybe_assign_investor_role(user: User, db: AsyncSession) -> None:
    """Upgrade user to investor role if their email matches a scored investor."""
    if user.role not in (UserRole.user, UserRole.investor):
        return  # Don't downgrade expert/admin/superadmin
    result = await db.execute(
        select(Investor).where(func.lower(Investor.email) == user.email.lower())
    )
    investor = result.scalar_one_or_none()
    if investor and user.role == UserRole.user:
        user.role = UserRole.investor
        await db.commit()


def make_token(user: User) -> str:
    return jwt.encode(
        {"sub": str(user.id), "email": user.email, "role": user.role.value},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


@router.post("/api/credentials/register")
async def register(body: RegisterIn, db: AsyncSession = Depends(get_db)):
    """Register a new user with email and password."""
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    # Check promo code for free unlimited subscription
    promo_valid = (
        body.promo_code
        and body.promo_code.strip().upper() == settings.promo_code_unlimited.upper()
    )

    user = User(
        email=body.email,
        name=body.name,
        auth_provider=AuthProvider.credentials,
        provider_id="credentials",
        password_hash=hash_password(body.password),
        ecosystem_role=body.ecosystem_role,
        region=body.region,
        subscription_status=SubscriptionStatus.active if promo_valid else SubscriptionStatus.none,
        subscription_tier=SubscriptionTier.unlimited if promo_valid else None,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    await _maybe_assign_investor_role(user, db)

    email_service.send_welcome(user_email=user.email, user_name=user.name)

    return {
        "token": make_token(user),
        "user": _user_dict(user),
        "promo_applied": bool(promo_valid),
    }


@router.post("/api/credentials/login")
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    """Login with email and password."""
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user is None or user.password_hash is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    await _maybe_assign_investor_role(user, db)

    return {"token": make_token(user), "user": _user_dict(user)}


@router.put("/api/me/profile")
async def update_my_profile(
    body: ProfileUpdateIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update current user's profile."""
    if body.name is not None:
        user.name = body.name
    if body.avatar_url is not None:
        user.avatar_url = body.avatar_url
    if body.ecosystem_role is not None:
        user.ecosystem_role = body.ecosystem_role
    if body.region is not None:
        user.region = body.region

    await db.commit()
    await db.refresh(user)

    return _user_dict(user)
