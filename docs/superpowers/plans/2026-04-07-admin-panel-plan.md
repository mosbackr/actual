# Admin Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the superadmin panel — a standalone Next.js app with backend extensions for managing startups, experts, DD templates, and expert assignments.

**Architecture:** Extends the existing FastAPI backend with new models, migration, and API endpoints for templates, dimensions, assignments, and auth token exchange. Adds a separate Next.js admin app (`admin/`) with sidebar navigation, triage feed, and CRUD pages for all admin functions.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Next.js 16, TypeScript, Tailwind CSS v4, NextAuth v4, Docker Compose, AWS CDK

**Spec:** `docs/superpowers/specs/2026-04-07-admin-panel-design.md`

**IMPORTANT (Next.js 16):** After running `npm install` in the admin app, read `node_modules/next/dist/docs/` for any breaking changes. Known differences from earlier versions: `searchParams` is `Promise<>` (must be awaited), Tailwind v4 uses `@import "tailwindcss"` (no `@tailwind` directives).

---

## File Structure

### Backend — New Files
- `backend/app/utils.py` — slugify utility
- `backend/app/models/template.py` — DueDiligenceTemplate, TemplateDimension
- `backend/app/models/assignment.py` — StartupAssignment, AssignmentStatus
- `backend/app/models/dimension.py` — StartupDimension
- `backend/app/api/auth_exchange.py` — POST /api/auth/token (OAuth → backend JWT)
- `backend/app/api/admin_templates.py` — Template CRUD (5 endpoints)
- `backend/app/api/admin_dimensions.py` — Startup dimension management (3 endpoints)
- `backend/app/api/admin_assignments.py` — Expert assignment admin (4 endpoints)
- `backend/app/api/expert_assignments.py` — Expert-facing assignment (3 endpoints)
- `backend/tests/test_auth_exchange.py`
- `backend/tests/test_admin_templates.py`
- `backend/tests/test_admin_dimensions.py`
- `backend/tests/test_admin_assignments.py`
- `backend/tests/test_expert_assignments.py`
- `backend/alembic/versions/*_admin_panel_tables.py`

### Backend — Modified Files
- `backend/app/models/__init__.py` — add new model exports
- `backend/app/models/startup.py` — add template_id FK
- `backend/app/api/admin.py` — enhance pipeline + users endpoints
- `backend/app/main.py` — register new routers
- `backend/app/config.py` — add localhost:3001 to CORS origins
- `backend/tests/test_admin.py` — add tests for enhanced endpoints

### Admin App — New Files (entire `admin/` directory)
- `admin/package.json`
- `admin/tsconfig.json`
- `admin/next.config.ts`
- `admin/postcss.config.mjs`
- `admin/Dockerfile`
- `admin/.env.local.example`
- `admin/types/next-auth.d.ts` — NextAuth type augmentations
- `admin/app/globals.css`
- `admin/app/layout.tsx`
- `admin/app/providers.tsx`
- `admin/app/page.tsx` — Triage feed
- `admin/app/api/auth/[...nextauth]/route.ts`
- `admin/app/startups/page.tsx`
- `admin/app/startups/[id]/page.tsx`
- `admin/app/experts/page.tsx`
- `admin/app/experts/[id]/page.tsx`
- `admin/app/templates/page.tsx`
- `admin/app/templates/new/page.tsx`
- `admin/app/templates/[id]/page.tsx`
- `admin/app/users/page.tsx`
- `admin/lib/auth.ts`
- `admin/lib/api.ts`
- `admin/lib/types.ts`
- `admin/components/Sidebar.tsx`
- `admin/components/AccessDenied.tsx`
- `admin/components/TriageFeedCard.tsx`
- `admin/components/StartupEditor.tsx`
- `admin/components/DimensionManager.tsx`
- `admin/components/ExpertPicker.tsx`
- `admin/components/TemplateEditor.tsx`
- `admin/components/StatusBadge.tsx`
- `admin/components/DataTable.tsx`

### Infrastructure — Modified Files
- `docker-compose.yml` — add admin service on port 3001
- `infra/stacks/acutal_stack.py` — add admin Fargate service

---

### Task 1: Backend Models + Utility

**Files:**
- Create: `backend/app/utils.py`
- Create: `backend/app/models/template.py`
- Create: `backend/app/models/assignment.py`
- Create: `backend/app/models/dimension.py`
- Modify: `backend/app/models/startup.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Create slugify utility**

Create `backend/app/utils.py`:

```python
import re


def slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")
```

- [ ] **Step 2: Create template model**

Create `backend/app/models/template.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.industry import Base


class DueDiligenceTemplate(Base):
    __tablename__ = "due_diligence_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    dimensions = relationship("TemplateDimension", back_populates="template", cascade="all, delete-orphan")


class TemplateDimension(Base):
    __tablename__ = "template_dimensions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("due_diligence_templates.id", ondelete="CASCADE"), nullable=False
    )
    dimension_name: Mapped[str] = mapped_column(String(255), nullable=False)
    dimension_slug: Mapped[str] = mapped_column(String(255), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    template = relationship("DueDiligenceTemplate", back_populates="dimensions")
```

- [ ] **Step 3: Create assignment model**

Create `backend/app/models/assignment.py`:

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.industry import Base


class AssignmentStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    declined = "declined"


class StartupAssignment(Base):
    __tablename__ = "startup_assignments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    startup_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("startups.id"), nullable=False)
    expert_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("expert_profiles.id"), nullable=False)
    assigned_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    status: Mapped[AssignmentStatus] = mapped_column(
        Enum(AssignmentStatus), nullable=False, default=AssignmentStatus.pending
    )
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    startup = relationship("Startup")
    expert = relationship("ExpertProfile")
    assigner = relationship("User", foreign_keys=[assigned_by])
```

- [ ] **Step 4: Create startup dimension model**

Create `backend/app/models/dimension.py`:

```python
import uuid

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.industry import Base


class StartupDimension(Base):
    __tablename__ = "startup_dimensions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    startup_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("startups.id"), nullable=False)
    dimension_name: Mapped[str] = mapped_column(String(255), nullable=False)
    dimension_slug: Mapped[str] = mapped_column(String(255), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
```

- [ ] **Step 5: Add template_id to Startup model**

In `backend/app/models/startup.py`, add this import at the top (with existing imports):

```python
from sqlalchemy import Column, Date, DateTime, Enum, Float, ForeignKey, String, Table, Text, func
```

Add this column to the `Startup` class, after `user_score`:

```python
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("due_diligence_templates.id"), nullable=True
    )
```

- [ ] **Step 6: Update models __init__.py**

Replace `backend/app/models/__init__.py` with:

```python
from app.models.user import User
from app.models.expert import ExpertProfile, expert_industries, expert_skills
from app.models.startup import Startup, startup_industries
from app.models.industry import Industry
from app.models.skill import Skill
from app.models.media import StartupMedia
from app.models.score import StartupScoreHistory
from app.models.template import DueDiligenceTemplate, TemplateDimension
from app.models.assignment import StartupAssignment
from app.models.dimension import StartupDimension

__all__ = [
    "User",
    "ExpertProfile",
    "expert_industries",
    "expert_skills",
    "Startup",
    "startup_industries",
    "Industry",
    "Skill",
    "StartupMedia",
    "StartupScoreHistory",
    "DueDiligenceTemplate",
    "TemplateDimension",
    "StartupAssignment",
    "StartupDimension",
]
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/utils.py backend/app/models/template.py backend/app/models/assignment.py backend/app/models/dimension.py backend/app/models/startup.py backend/app/models/__init__.py
git commit -m "feat: add models for DD templates, assignments, and startup dimensions"
```

---

### Task 2: Alembic Migration

**Files:**
- Create: `backend/alembic/versions/*_admin_panel_tables.py`

- [ ] **Step 1: Generate the migration**

```bash
cd backend
alembic revision --autogenerate -m "admin panel tables"
```

This should detect:
- New table `due_diligence_templates`
- New table `template_dimensions`
- New table `startup_assignments`
- New table `startup_dimensions`
- New column `startups.template_id`

- [ ] **Step 2: Review the generated migration**

Open the generated file in `backend/alembic/versions/` and verify it contains all 4 new tables and the `template_id` column addition. The migration should look like:

```python
def upgrade() -> None:
    op.create_table('due_diligence_templates',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
        sa.UniqueConstraint('slug')
    )
    op.create_table('startup_dimensions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('startup_id', sa.UUID(), nullable=False),
        sa.Column('dimension_name', sa.String(length=255), nullable=False),
        sa.Column('dimension_slug', sa.String(length=255), nullable=False),
        sa.Column('weight', sa.Float(), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['startup_id'], ['startups.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('template_dimensions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('template_id', sa.UUID(), nullable=False),
        sa.Column('dimension_name', sa.String(length=255), nullable=False),
        sa.Column('dimension_slug', sa.String(length=255), nullable=False),
        sa.Column('weight', sa.Float(), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['template_id'], ['due_diligence_templates.id', ], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('startup_assignments',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('startup_id', sa.UUID(), nullable=False),
        sa.Column('expert_id', sa.UUID(), nullable=False),
        sa.Column('assigned_by', sa.UUID(), nullable=False),
        sa.Column('status', sa.Enum('pending', 'accepted', 'declined', name='assignmentstatus'), nullable=False),
        sa.Column('assigned_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('responded_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['assigned_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['expert_id'], ['expert_profiles.id'], ),
        sa.ForeignKeyConstraint(['startup_id'], ['startups.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.add_column('startups', sa.Column('template_id', sa.UUID(), nullable=True))
    op.create_foreign_key(None, 'startups', 'due_diligence_templates', ['template_id'], ['id'])
```

- [ ] **Step 3: Run migration against local DB**

```bash
cd backend
alembic upgrade head
```

Expected: Migration applies successfully.

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/
git commit -m "feat: add migration for admin panel tables"
```

---

### Task 3: Auth Token Exchange Endpoint + Tests

**Files:**
- Create: `backend/app/api/auth_exchange.py`
- Create: `backend/tests/test_auth_exchange.py`

The admin app (and main frontend) need a way to exchange OAuth credentials for a backend JWT. NextAuth handles OAuth, then calls this endpoint to get a JWT the FastAPI backend can validate.

- [ ] **Step 1: Write tests**

Create `backend/tests/test_auth_exchange.py`:

```python
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import AuthProvider, User, UserRole


@pytest.mark.asyncio
async def test_token_exchange_creates_new_user(client: AsyncClient):
    resp = await client.post("/api/auth/token", json={
        "email": "newuser@example.com",
        "name": "New User",
        "provider": "google",
        "provider_id": "google-new-123",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "token" in data
    assert data["user"]["email"] == "newuser@example.com"
    assert data["user"]["role"] == "user"


@pytest.mark.asyncio
async def test_token_exchange_returns_existing_user(client: AsyncClient, admin_user: User):
    resp = await client.post("/api/auth/token", json={
        "email": admin_user.email,
        "name": admin_user.name,
        "provider": "google",
        "provider_id": "google-admin",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["user"]["id"] == str(admin_user.id)
    assert data["user"]["role"] == "superadmin"


@pytest.mark.asyncio
async def test_token_exchange_token_is_valid_jwt(client: AsyncClient):
    resp = await client.post("/api/auth/token", json={
        "email": "jwttest@example.com",
        "name": "JWT Test",
        "provider": "github",
        "provider_id": "gh-456",
    })
    token = resp.json()["token"]
    # Use the token to call /api/me
    me_resp = await client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "jwttest@example.com"


@pytest.mark.asyncio
async def test_token_exchange_missing_fields(client: AsyncClient):
    resp = await client.post("/api/auth/token", json={"email": "bad@example.com"})
    assert resp.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_auth_exchange.py -v
```

Expected: FAIL — module `app.api.auth_exchange` not found or routes not registered.

- [ ] **Step 3: Write implementation**

Create `backend/app/api/auth_exchange.py`:

```python
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
```

- [ ] **Step 4: Register the router temporarily for testing**

Add to `backend/app/main.py` (after existing imports):

```python
from app.api.auth_exchange import router as auth_exchange_router
```

And add (after existing `include_router` calls):

```python
app.include_router(auth_exchange_router)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_auth_exchange.py -v
```

Expected: All 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/auth_exchange.py backend/tests/test_auth_exchange.py backend/app/main.py
git commit -m "feat: add auth token exchange endpoint for NextAuth integration"
```

---

### Task 4: Template CRUD API + Tests

**Files:**
- Create: `backend/app/api/admin_templates.py`
- Create: `backend/tests/test_admin_templates.py`

- [ ] **Step 1: Write tests**

Create `backend/tests/test_admin_templates.py`:

```python
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.template import DueDiligenceTemplate, TemplateDimension
from app.models.user import User
from app.utils import slugify
from tests.conftest import make_jwt_header


@pytest_asyncio.fixture
async def sample_template(db: AsyncSession) -> DueDiligenceTemplate:
    t = DueDiligenceTemplate(
        id=uuid.uuid4(),
        name="SaaS",
        slug="saas",
        description="SaaS startup evaluation",
    )
    db.add(t)
    await db.flush()
    dims = [
        TemplateDimension(
            template_id=t.id,
            dimension_name="Market Size",
            dimension_slug="market-size",
            weight=1.5,
            sort_order=0,
        ),
        TemplateDimension(
            template_id=t.id,
            dimension_name="Technical Moat",
            dimension_slug="technical-moat",
            weight=1.0,
            sort_order=1,
        ),
    ]
    db.add_all(dims)
    await db.commit()
    await db.refresh(t)
    return t


@pytest.mark.asyncio
async def test_list_templates(client: AsyncClient, admin_user: User, sample_template: DueDiligenceTemplate):
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.get("/api/admin/dd-templates", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert any(t["slug"] == "saas" for t in data)


@pytest.mark.asyncio
async def test_create_template(client: AsyncClient, admin_user: User):
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.post("/api/admin/dd-templates", json={
        "name": "BioTech",
        "description": "Biotech startup evaluation",
        "dimensions": [
            {"dimension_name": "Regulatory Path", "weight": 2.0, "sort_order": 0},
            {"dimension_name": "Clinical Pipeline", "weight": 1.5, "sort_order": 1},
        ],
    }, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "BioTech"
    assert data["slug"] == "biotech"
    assert len(data["dimensions"]) == 2
    assert data["dimensions"][0]["dimension_slug"] == "regulatory-path"


@pytest.mark.asyncio
async def test_get_template(client: AsyncClient, admin_user: User, sample_template: DueDiligenceTemplate):
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.get(f"/api/admin/dd-templates/{sample_template.id}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "SaaS"
    assert len(data["dimensions"]) == 2


@pytest.mark.asyncio
async def test_update_template(client: AsyncClient, admin_user: User, sample_template: DueDiligenceTemplate):
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.put(f"/api/admin/dd-templates/{sample_template.id}", json={
        "name": "SaaS Updated",
        "description": "Updated description",
        "dimensions": [
            {"dimension_name": "Revenue Model", "weight": 2.0, "sort_order": 0},
        ],
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "SaaS Updated"
    assert len(data["dimensions"]) == 1
    assert data["dimensions"][0]["dimension_name"] == "Revenue Model"


@pytest.mark.asyncio
async def test_delete_template(client: AsyncClient, admin_user: User, sample_template: DueDiligenceTemplate):
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.delete(f"/api/admin/dd-templates/{sample_template.id}", headers=headers)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_template_in_use(
    client: AsyncClient, admin_user: User, sample_template: DueDiligenceTemplate, db: AsyncSession
):
    """Cannot delete a template referenced by a startup."""
    from app.models.startup import Startup, StartupStage, StartupStatus

    s = Startup(
        id=uuid.uuid4(), name="TestCo", slug="testco", description="Test",
        stage=StartupStage.seed, status=StartupStatus.pending,
        template_id=sample_template.id,
    )
    db.add(s)
    await db.commit()
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.delete(f"/api/admin/dd-templates/{sample_template.id}", headers=headers)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_non_admin_cannot_access_templates(client: AsyncClient, test_user: User):
    headers = make_jwt_header(str(test_user.id), test_user.email, "user")
    resp = await client.get("/api/admin/dd-templates", headers=headers)
    assert resp.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_admin_templates.py -v
```

Expected: FAIL — routes not found.

- [ ] **Step 3: Write implementation**

Create `backend/app/api/admin_templates.py`:

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select
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
    dimensions: list[DimensionIn] = []


class TemplateUpdateIn(BaseModel):
    name: str
    description: str | None = None
    dimensions: list[DimensionIn] = []


def _serialize_template(t: DueDiligenceTemplate) -> dict:
    return {
        "id": str(t.id),
        "name": t.name,
        "slug": t.slug,
        "description": t.description,
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

    # Full replace of dimensions
    for dim in template.dimensions:
        await db.delete(dim)
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

    # Check if any startups reference this template
    startup_result = await db.execute(
        select(Startup).where(Startup.template_id == template_id).limit(1)
    )
    if startup_result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Template is in use by one or more startups")

    await db.delete(template)
    await db.commit()
    return Response(status_code=204)
```

- [ ] **Step 4: Register router in main.py**

Add to `backend/app/main.py`:

```python
from app.api.admin_templates import router as admin_templates_router
```

```python
app.include_router(admin_templates_router)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_admin_templates.py -v
```

Expected: All 8 tests PASS.

- [ ] **Step 6: Run all existing tests to check for regressions**

```bash
cd backend && python -m pytest -v
```

Expected: All tests PASS (existing + new).

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/admin_templates.py backend/tests/test_admin_templates.py backend/app/main.py
git commit -m "feat: add DD template CRUD API with tests"
```

---

### Task 5: Startup Dimensions API + Tests

**Files:**
- Create: `backend/app/api/admin_dimensions.py`
- Create: `backend/tests/test_admin_dimensions.py`

- [ ] **Step 1: Write tests**

Create `backend/tests/test_admin_dimensions.py`:

```python
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dimension import StartupDimension
from app.models.startup import Startup, StartupStage, StartupStatus
from app.models.template import DueDiligenceTemplate, TemplateDimension
from app.models.user import User
from tests.conftest import make_jwt_header


@pytest_asyncio.fixture
async def startup_for_dims(db: AsyncSession) -> Startup:
    s = Startup(
        id=uuid.uuid4(),
        name="DimTest Startup",
        slug="dimtest-startup",
        description="For dimension tests",
        stage=StartupStage.seed,
        status=StartupStatus.pending,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


@pytest_asyncio.fixture
async def template_for_apply(db: AsyncSession) -> DueDiligenceTemplate:
    t = DueDiligenceTemplate(id=uuid.uuid4(), name="FinTech", slug="fintech", description="FinTech eval")
    db.add(t)
    await db.flush()
    db.add_all([
        TemplateDimension(
            template_id=t.id, dimension_name="Regulatory Compliance",
            dimension_slug="regulatory-compliance", weight=2.0, sort_order=0,
        ),
        TemplateDimension(
            template_id=t.id, dimension_name="Market Fit",
            dimension_slug="market-fit", weight=1.0, sort_order=1,
        ),
    ])
    await db.commit()
    await db.refresh(t)
    return t


@pytest.mark.asyncio
async def test_apply_template(
    client: AsyncClient, admin_user: User,
    startup_for_dims: Startup, template_for_apply: DueDiligenceTemplate,
):
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.post(
        f"/api/admin/startups/{startup_for_dims.id}/apply-template",
        json={"template_id": str(template_for_apply.id)},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["dimensions"]) == 2
    assert data["template_id"] == str(template_for_apply.id)


@pytest.mark.asyncio
async def test_get_dimensions(
    client: AsyncClient, admin_user: User, startup_for_dims: Startup, db: AsyncSession,
):
    db.add(StartupDimension(
        startup_id=startup_for_dims.id, dimension_name="Team",
        dimension_slug="team", weight=1.0, sort_order=0,
    ))
    await db.commit()
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.get(
        f"/api/admin/startups/{startup_for_dims.id}/dimensions", headers=headers,
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["dimension_name"] == "Team"


@pytest.mark.asyncio
async def test_update_dimensions(
    client: AsyncClient, admin_user: User, startup_for_dims: Startup,
):
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.put(
        f"/api/admin/startups/{startup_for_dims.id}/dimensions",
        json={"dimensions": [
            {"dimension_name": "Scalability", "weight": 1.5, "sort_order": 0},
            {"dimension_name": "Unit Economics", "weight": 2.0, "sort_order": 1},
        ]},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["dimension_name"] == "Scalability"
    assert data[1]["dimension_slug"] == "unit-economics"


@pytest.mark.asyncio
async def test_apply_template_not_found(client: AsyncClient, admin_user: User, startup_for_dims: Startup):
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.post(
        f"/api/admin/startups/{startup_for_dims.id}/apply-template",
        json={"template_id": str(uuid.uuid4())},
        headers=headers,
    )
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_admin_dimensions.py -v
```

Expected: FAIL — routes not found.

- [ ] **Step 3: Write implementation**

Create `backend/app/api/admin_dimensions.py`:

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_role
from app.db.session import get_db
from app.models.dimension import StartupDimension
from app.models.startup import Startup
from app.models.template import DueDiligenceTemplate, TemplateDimension
from app.models.user import User
from app.utils import slugify

router = APIRouter()


class DimensionIn(BaseModel):
    dimension_name: str
    weight: float = 1.0
    sort_order: int = 0


class ApplyTemplateIn(BaseModel):
    template_id: str


class UpdateDimensionsIn(BaseModel):
    dimensions: list[DimensionIn]


def _serialize_dimensions(dims: list[StartupDimension]) -> list[dict]:
    return [
        {
            "id": str(d.id),
            "dimension_name": d.dimension_name,
            "dimension_slug": d.dimension_slug,
            "weight": d.weight,
            "sort_order": d.sort_order,
        }
        for d in sorted(dims, key=lambda d: d.sort_order)
    ]


@router.post("/api/admin/startups/{startup_id}/apply-template")
async def apply_template(
    startup_id: uuid.UUID,
    body: ApplyTemplateIn,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Startup).where(Startup.id == startup_id))
    startup = result.scalar_one_or_none()
    if startup is None:
        raise HTTPException(status_code=404, detail="Startup not found")

    template_result = await db.execute(
        select(DueDiligenceTemplate)
        .options(selectinload(DueDiligenceTemplate.dimensions))
        .where(DueDiligenceTemplate.id == uuid.UUID(body.template_id))
    )
    template = template_result.scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    # Delete existing dimensions for this startup
    existing = await db.execute(
        select(StartupDimension).where(StartupDimension.startup_id == startup_id)
    )
    for dim in existing.scalars().all():
        await db.delete(dim)

    # Copy dimensions from template
    new_dims = []
    for td in template.dimensions:
        sd = StartupDimension(
            startup_id=startup_id,
            dimension_name=td.dimension_name,
            dimension_slug=td.dimension_slug,
            weight=td.weight,
            sort_order=td.sort_order,
        )
        db.add(sd)
        new_dims.append(sd)

    startup.template_id = template.id
    await db.commit()

    return {
        "template_id": str(template.id),
        "dimensions": _serialize_dimensions(new_dims),
    }


@router.get("/api/admin/startups/{startup_id}/dimensions")
async def get_dimensions(
    startup_id: uuid.UUID,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Startup).where(Startup.id == startup_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Startup not found")

    dims_result = await db.execute(
        select(StartupDimension)
        .where(StartupDimension.startup_id == startup_id)
        .order_by(StartupDimension.sort_order)
    )
    return _serialize_dimensions(list(dims_result.scalars().all()))


@router.put("/api/admin/startups/{startup_id}/dimensions")
async def update_dimensions(
    startup_id: uuid.UUID,
    body: UpdateDimensionsIn,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Startup).where(Startup.id == startup_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Startup not found")

    # Delete existing
    existing = await db.execute(
        select(StartupDimension).where(StartupDimension.startup_id == startup_id)
    )
    for dim in existing.scalars().all():
        await db.delete(dim)
    await db.flush()

    # Create new
    new_dims = []
    for d in body.dimensions:
        sd = StartupDimension(
            startup_id=startup_id,
            dimension_name=d.dimension_name,
            dimension_slug=slugify(d.dimension_name),
            weight=d.weight,
            sort_order=d.sort_order,
        )
        db.add(sd)
        new_dims.append(sd)

    await db.commit()
    return _serialize_dimensions(new_dims)
```

- [ ] **Step 4: Register router in main.py**

Add to `backend/app/main.py`:

```python
from app.api.admin_dimensions import router as admin_dimensions_router
```

```python
app.include_router(admin_dimensions_router)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_admin_dimensions.py -v
```

Expected: All 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/admin_dimensions.py backend/tests/test_admin_dimensions.py backend/app/main.py
git commit -m "feat: add startup dimension management API with tests"
```

---

### Task 6: Expert Assignment Admin API + Tests

**Files:**
- Create: `backend/app/api/admin_assignments.py`
- Create: `backend/tests/test_admin_assignments.py`

- [ ] **Step 1: Write tests**

Create `backend/tests/test_admin_assignments.py`:

```python
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assignment import StartupAssignment, AssignmentStatus
from app.models.expert import ApplicationStatus, ExpertProfile
from app.models.startup import Startup, StartupStage, StartupStatus
from app.models.user import AuthProvider, User, UserRole
from tests.conftest import make_jwt_header


@pytest_asyncio.fixture
async def approved_expert(db: AsyncSession) -> tuple[User, ExpertProfile]:
    user = User(
        id=uuid.uuid4(), email="expert@example.com", name="Expert User",
        auth_provider=AuthProvider.linkedin, provider_id="li-expert",
        role=UserRole.expert,
    )
    db.add(user)
    await db.flush()
    profile = ExpertProfile(
        id=uuid.uuid4(), user_id=user.id, bio="Domain expert",
        years_experience=15, application_status=ApplicationStatus.approved,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(user)
    await db.refresh(profile)
    return user, profile


@pytest_asyncio.fixture
async def assignable_startup(db: AsyncSession) -> Startup:
    s = Startup(
        id=uuid.uuid4(), name="Assignable Co", slug="assignable-co",
        description="For assignment tests", stage=StartupStage.series_a,
        status=StartupStatus.approved,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


@pytest.mark.asyncio
async def test_assign_expert(
    client: AsyncClient, admin_user: User,
    approved_expert: tuple, assignable_startup: Startup,
):
    _, profile = approved_expert
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.post(
        f"/api/admin/startups/{assignable_startup.id}/assign-expert",
        json={"expert_id": str(profile.id)},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "pending"
    assert data["expert_id"] == str(profile.id)


@pytest.mark.asyncio
async def test_list_assignments(
    client: AsyncClient, admin_user: User,
    approved_expert: tuple, assignable_startup: Startup, db: AsyncSession,
):
    _, profile = approved_expert
    db.add(StartupAssignment(
        startup_id=assignable_startup.id, expert_id=profile.id,
        assigned_by=admin_user.id,
    ))
    await db.commit()
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.get(
        f"/api/admin/startups/{assignable_startup.id}/assignments", headers=headers,
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_delete_assignment(
    client: AsyncClient, admin_user: User,
    approved_expert: tuple, assignable_startup: Startup, db: AsyncSession,
):
    _, profile = approved_expert
    assignment = StartupAssignment(
        id=uuid.uuid4(), startup_id=assignable_startup.id,
        expert_id=profile.id, assigned_by=admin_user.id,
    )
    db.add(assignment)
    await db.commit()
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.delete(f"/api/admin/assignments/{assignment.id}", headers=headers)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_list_approved_experts(client: AsyncClient, admin_user: User, approved_expert: tuple):
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.get("/api/admin/experts", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["application_status"] == "approved"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_admin_assignments.py -v
```

- [ ] **Step 3: Write implementation**

Create `backend/app/api/admin_assignments.py`:

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_role
from app.db.session import get_db
from app.models.assignment import StartupAssignment
from app.models.expert import ApplicationStatus, ExpertProfile
from app.models.startup import Startup
from app.models.user import User

router = APIRouter()


class AssignExpertIn(BaseModel):
    expert_id: str


@router.post("/api/admin/startups/{startup_id}/assign-expert", status_code=201)
async def assign_expert(
    startup_id: uuid.UUID,
    body: AssignExpertIn,
    admin: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Startup).where(Startup.id == startup_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Startup not found")

    expert_id = uuid.UUID(body.expert_id)
    result = await db.execute(select(ExpertProfile).where(ExpertProfile.id == expert_id))
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Expert not found")
    if profile.application_status != ApplicationStatus.approved:
        raise HTTPException(status_code=400, detail="Expert is not approved")

    assignment = StartupAssignment(
        startup_id=startup_id,
        expert_id=expert_id,
        assigned_by=admin.id,
    )
    db.add(assignment)
    await db.commit()
    await db.refresh(assignment)

    return {
        "id": str(assignment.id),
        "startup_id": str(assignment.startup_id),
        "expert_id": str(assignment.expert_id),
        "assigned_by": str(assignment.assigned_by),
        "status": assignment.status.value,
        "assigned_at": assignment.assigned_at.isoformat(),
    }


@router.get("/api/admin/startups/{startup_id}/assignments")
async def list_assignments(
    startup_id: uuid.UUID,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StartupAssignment)
        .where(StartupAssignment.startup_id == startup_id)
        .order_by(StartupAssignment.assigned_at.desc())
    )
    assignments = result.scalars().all()
    return [
        {
            "id": str(a.id),
            "startup_id": str(a.startup_id),
            "expert_id": str(a.expert_id),
            "assigned_by": str(a.assigned_by),
            "status": a.status.value,
            "assigned_at": a.assigned_at.isoformat(),
            "responded_at": a.responded_at.isoformat() if a.responded_at else None,
        }
        for a in assignments
    ]


@router.delete("/api/admin/assignments/{assignment_id}", status_code=204)
async def delete_assignment(
    assignment_id: uuid.UUID,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StartupAssignment).where(StartupAssignment.id == assignment_id)
    )
    assignment = result.scalar_one_or_none()
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    await db.delete(assignment)
    await db.commit()
    return Response(status_code=204)


@router.get("/api/admin/experts")
async def list_approved_experts(
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ExpertProfile)
        .options(selectinload(ExpertProfile.industries), selectinload(ExpertProfile.skills))
        .where(ExpertProfile.application_status == ApplicationStatus.approved)
        .order_by(ExpertProfile.created_at.desc())
    )
    profiles = result.scalars().all()
    return [
        {
            "id": str(p.id),
            "user_id": str(p.user_id),
            "bio": p.bio,
            "years_experience": p.years_experience,
            "application_status": p.application_status.value,
            "industries": [{"id": str(i.id), "name": i.name, "slug": i.slug} for i in p.industries],
            "skills": [{"id": str(s.id), "name": s.name, "slug": s.slug} for s in p.skills],
            "created_at": p.created_at.isoformat(),
        }
        for p in profiles
    ]
```

- [ ] **Step 4: Register router in main.py**

Add to `backend/app/main.py`:

```python
from app.api.admin_assignments import router as admin_assignments_router
```

```python
app.include_router(admin_assignments_router)
```

- [ ] **Step 5: Run tests**

```bash
cd backend && python -m pytest tests/test_admin_assignments.py -v
```

Expected: All 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/admin_assignments.py backend/tests/test_admin_assignments.py backend/app/main.py
git commit -m "feat: add expert assignment admin API with tests"
```

---

### Task 7: Expert-Facing Assignment API + Tests

**Files:**
- Create: `backend/app/api/expert_assignments.py`
- Create: `backend/tests/test_expert_assignments.py`

- [ ] **Step 1: Write tests**

Create `backend/tests/test_expert_assignments.py`:

```python
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assignment import AssignmentStatus, StartupAssignment
from app.models.expert import ApplicationStatus, ExpertProfile
from app.models.startup import Startup, StartupStage, StartupStatus
from app.models.user import AuthProvider, User, UserRole
from tests.conftest import make_jwt_header


@pytest_asyncio.fixture
async def expert_with_assignment(db: AsyncSession):
    admin = User(
        id=uuid.uuid4(), email="assigner@example.com", name="Admin",
        auth_provider=AuthProvider.google, provider_id="g-admin2",
        role=UserRole.superadmin,
    )
    expert_user = User(
        id=uuid.uuid4(), email="myexpert@example.com", name="My Expert",
        auth_provider=AuthProvider.github, provider_id="gh-expert",
        role=UserRole.expert,
    )
    db.add_all([admin, expert_user])
    await db.flush()

    profile = ExpertProfile(
        id=uuid.uuid4(), user_id=expert_user.id, bio="Expert bio",
        years_experience=10, application_status=ApplicationStatus.approved,
    )
    db.add(profile)
    await db.flush()

    startup = Startup(
        id=uuid.uuid4(), name="Assigned Startup", slug="assigned-startup",
        description="Test", stage=StartupStage.seed, status=StartupStatus.approved,
    )
    db.add(startup)
    await db.flush()

    assignment = StartupAssignment(
        id=uuid.uuid4(), startup_id=startup.id, expert_id=profile.id,
        assigned_by=admin.id,
    )
    db.add(assignment)
    await db.commit()

    await db.refresh(expert_user)
    await db.refresh(profile)
    await db.refresh(assignment)
    return expert_user, profile, assignment


@pytest.mark.asyncio
async def test_expert_list_assignments(client: AsyncClient, expert_with_assignment):
    user, profile, assignment = expert_with_assignment
    headers = make_jwt_header(str(user.id), user.email, "expert")
    resp = await client.get("/api/expert/assignments", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["id"] == str(assignment.id)


@pytest.mark.asyncio
async def test_expert_accept_assignment(client: AsyncClient, expert_with_assignment):
    user, profile, assignment = expert_with_assignment
    headers = make_jwt_header(str(user.id), user.email, "expert")
    resp = await client.put(f"/api/expert/assignments/{assignment.id}/accept", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"
    assert resp.json()["responded_at"] is not None


@pytest.mark.asyncio
async def test_expert_decline_assignment(client: AsyncClient, expert_with_assignment):
    user, profile, assignment = expert_with_assignment
    headers = make_jwt_header(str(user.id), user.email, "expert")
    resp = await client.put(f"/api/expert/assignments/{assignment.id}/decline", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "declined"


@pytest.mark.asyncio
async def test_non_expert_cannot_access(client: AsyncClient, test_user: User):
    headers = make_jwt_header(str(test_user.id), test_user.email, "user")
    resp = await client.get("/api/expert/assignments", headers=headers)
    assert resp.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_expert_assignments.py -v
```

- [ ] **Step 3: Write implementation**

Create `backend/app/api/expert_assignments.py`:

```python
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.db.session import get_db
from app.models.assignment import AssignmentStatus, StartupAssignment
from app.models.expert import ExpertProfile
from app.models.user import User

router = APIRouter()


@router.get("/api/expert/assignments")
async def my_assignments(
    user: User = Depends(require_role("expert")),
    db: AsyncSession = Depends(get_db),
):
    # Find expert profile for this user
    result = await db.execute(
        select(ExpertProfile).where(ExpertProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Expert profile not found")

    assignments_result = await db.execute(
        select(StartupAssignment)
        .where(StartupAssignment.expert_id == profile.id)
        .order_by(StartupAssignment.assigned_at.desc())
    )
    assignments = assignments_result.scalars().all()
    return [
        {
            "id": str(a.id),
            "startup_id": str(a.startup_id),
            "expert_id": str(a.expert_id),
            "status": a.status.value,
            "assigned_at": a.assigned_at.isoformat(),
            "responded_at": a.responded_at.isoformat() if a.responded_at else None,
        }
        for a in assignments
    ]


@router.put("/api/expert/assignments/{assignment_id}/accept")
async def accept_assignment(
    assignment_id: uuid.UUID,
    user: User = Depends(require_role("expert")),
    db: AsyncSession = Depends(get_db),
):
    profile_result = await db.execute(
        select(ExpertProfile).where(ExpertProfile.user_id == user.id)
    )
    profile = profile_result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Expert profile not found")

    result = await db.execute(
        select(StartupAssignment).where(StartupAssignment.id == assignment_id)
    )
    assignment = result.scalar_one_or_none()
    if assignment is None or assignment.expert_id != profile.id:
        raise HTTPException(status_code=404, detail="Assignment not found")

    assignment.status = AssignmentStatus.accepted
    assignment.responded_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(assignment)

    return {
        "id": str(assignment.id),
        "startup_id": str(assignment.startup_id),
        "status": assignment.status.value,
        "responded_at": assignment.responded_at.isoformat(),
    }


@router.put("/api/expert/assignments/{assignment_id}/decline")
async def decline_assignment(
    assignment_id: uuid.UUID,
    user: User = Depends(require_role("expert")),
    db: AsyncSession = Depends(get_db),
):
    profile_result = await db.execute(
        select(ExpertProfile).where(ExpertProfile.user_id == user.id)
    )
    profile = profile_result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Expert profile not found")

    result = await db.execute(
        select(StartupAssignment).where(StartupAssignment.id == assignment_id)
    )
    assignment = result.scalar_one_or_none()
    if assignment is None or assignment.expert_id != profile.id:
        raise HTTPException(status_code=404, detail="Assignment not found")

    assignment.status = AssignmentStatus.declined
    assignment.responded_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(assignment)

    return {
        "id": str(assignment.id),
        "startup_id": str(assignment.startup_id),
        "status": assignment.status.value,
        "responded_at": assignment.responded_at.isoformat(),
    }
```

- [ ] **Step 4: Register router in main.py**

Add to `backend/app/main.py`:

```python
from app.api.expert_assignments import router as expert_assignments_router
```

```python
app.include_router(expert_assignments_router)
```

- [ ] **Step 5: Run tests**

```bash
cd backend && python -m pytest tests/test_expert_assignments.py -v
```

Expected: All 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/expert_assignments.py backend/tests/test_expert_assignments.py backend/app/main.py
git commit -m "feat: add expert-facing assignment API with tests"
```

---

### Task 8: Enhance Existing Admin Endpoints + Tests

**Files:**
- Modify: `backend/app/api/admin.py`
- Modify: `backend/tests/test_admin.py`

Enhance `GET /api/admin/startups/pipeline` with industry tags, assignment count, and dimensions_configured flag. Add `?role=` filter to `GET /api/admin/users`.

- [ ] **Step 1: Add new tests to test_admin.py**

Append to `backend/tests/test_admin.py`:

```python
@pytest.mark.asyncio
async def test_admin_pipeline_enriched(
    client: AsyncClient, admin_user: User, pending_startup: Startup, db: AsyncSession,
):
    """Pipeline response includes industry tags, assignment_count, dimensions_configured."""
    from app.models.industry import Industry
    from app.models.startup import startup_industries

    ind = Industry(id=uuid.uuid4(), name="TestInd", slug="testind")
    db.add(ind)
    await db.flush()
    await db.execute(startup_industries.insert().values(
        startup_id=pending_startup.id, industry_id=ind.id,
    ))
    await db.commit()

    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.get("/api/admin/startups/pipeline", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    item = next(s for s in data if s["id"] == str(pending_startup.id))
    assert "industries" in item
    assert "assignment_count" in item
    assert "dimensions_configured" in item
    assert len(item["industries"]) == 1


@pytest.mark.asyncio
async def test_admin_users_filter_by_role(client: AsyncClient, admin_user: User, test_user: User):
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.get("/api/admin/users?role=superadmin", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert all(u["role"] == "superadmin" for u in data)
    assert any(u["id"] == str(admin_user.id) for u in data)
```

- [ ] **Step 2: Run new tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_admin.py::test_admin_pipeline_enriched tests/test_admin.py::test_admin_users_filter_by_role -v
```

- [ ] **Step 3: Update admin.py — enhance pipeline endpoint**

Replace the `startup_pipeline` function in `backend/app/api/admin.py`:

```python
@router.get("/api/admin/startups/pipeline")
async def startup_pipeline(
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy.orm import selectinload
    from app.models.assignment import StartupAssignment
    from app.models.dimension import StartupDimension

    result = await db.execute(
        select(Startup)
        .options(selectinload(Startup.industries))
        .where(Startup.status == StartupStatus.pending)
        .order_by(Startup.created_at.desc())
    )
    startups = result.scalars().all()

    response = []
    for s in startups:
        # Count assignments
        assign_result = await db.execute(
            select(StartupAssignment).where(StartupAssignment.startup_id == s.id)
        )
        assignment_count = len(assign_result.scalars().all())

        # Check if dimensions configured
        dim_result = await db.execute(
            select(StartupDimension).where(StartupDimension.startup_id == s.id).limit(1)
        )
        dimensions_configured = dim_result.scalar_one_or_none() is not None

        response.append({
            "id": str(s.id),
            "name": s.name,
            "slug": s.slug,
            "description": s.description,
            "stage": s.stage.value,
            "status": s.status.value,
            "created_at": s.created_at.isoformat(),
            "industries": [{"id": str(i.id), "name": i.name, "slug": i.slug} for i in s.industries],
            "assignment_count": assignment_count,
            "dimensions_configured": dimensions_configured,
        })
    return response
```

- [ ] **Step 4: Update admin.py — add role filter to list_users**

Replace the `list_users` function in `backend/app/api/admin.py`:

```python
@router.get("/api/admin/users")
async def list_users(
    role: str | None = None,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    query = select(User).order_by(User.created_at.desc())
    if role is not None:
        query = query.where(User.role == UserRole(role))
    result = await db.execute(query)
    users = result.scalars().all()
    return [
        {"id": str(u.id), "email": u.email, "name": u.name, "role": u.role.value}
        for u in users
    ]
```

- [ ] **Step 5: Add missing imports to admin.py**

Ensure these imports are at the top of `backend/app/api/admin.py`:

```python
from app.models.user import User, UserRole
```

(UserRole was not imported before — add it.)

- [ ] **Step 6: Run all admin tests**

```bash
cd backend && python -m pytest tests/test_admin.py -v
```

Expected: All tests PASS (8 existing + 2 new = 10).

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/admin.py backend/tests/test_admin.py
git commit -m "feat: enhance admin pipeline with industries/assignments/dimensions, add role filter to users"
```

---

### Task 9: Register All Routers + Config Update

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/config.py`

- [ ] **Step 1: Verify main.py has all routers**

`backend/app/main.py` should now look like this (if not, update it):

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.users import router as users_router
from app.api.admin import router as admin_router
from app.api.startups import router as startups_router
from app.api.industries import router as industries_router
from app.api.experts import router as experts_router
from app.api.auth_exchange import router as auth_exchange_router
from app.api.admin_templates import router as admin_templates_router
from app.api.admin_dimensions import router as admin_dimensions_router
from app.api.admin_assignments import router as admin_assignments_router
from app.api.expert_assignments import router as expert_assignments_router

app = FastAPI(title="Acutal API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users_router)
app.include_router(admin_router)
app.include_router(startups_router)
app.include_router(industries_router)
app.include_router(experts_router)
app.include_router(auth_exchange_router)
app.include_router(admin_templates_router)
app.include_router(admin_dimensions_router)
app.include_router(admin_assignments_router)
app.include_router(expert_assignments_router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 2: Add admin app origin to CORS config**

Update `backend/app/config.py`:

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://acutal:acutal@localhost:5432/acutal"
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:3001"]

    model_config = {"env_prefix": "ACUTAL_"}


settings = Settings()
```

- [ ] **Step 3: Run full test suite**

```bash
cd backend && python -m pytest -v
```

Expected: All tests PASS (existing + new).

- [ ] **Step 4: Commit**

```bash
git add backend/app/main.py backend/app/config.py
git commit -m "feat: register all new routers and add admin CORS origin"
```

---

### Task 10: Admin App Scaffold

**Files:**
- Create: `admin/package.json`
- Create: `admin/tsconfig.json`
- Create: `admin/next.config.ts`
- Create: `admin/postcss.config.mjs`
- Create: `admin/Dockerfile`
- Create: `admin/.env.local.example`

- [ ] **Step 1: Create package.json**

Create `admin/package.json`:

```json
{
  "name": "admin",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev --port 3001",
    "build": "next build",
    "start": "next start --port 3001",
    "lint": "eslint"
  },
  "dependencies": {
    "next": "16.2.2",
    "next-auth": "^4.24.13",
    "react": "19.2.4",
    "react-dom": "19.2.4"
  },
  "devDependencies": {
    "@tailwindcss/postcss": "^4",
    "@types/node": "^20",
    "@types/react": "^19",
    "@types/react-dom": "^19",
    "eslint": "^9",
    "eslint-config-next": "16.2.2",
    "tailwindcss": "^4",
    "typescript": "^5"
  }
}
```

- [ ] **Step 2: Create tsconfig.json**

Create `admin/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2017",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "paths": {
      "@/*": ["./*"]
    }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

- [ ] **Step 3: Create next.config.ts**

Create `admin/next.config.ts`:

```typescript
import type { NextConfig } from "next";

const nextConfig: NextConfig = {};

export default nextConfig;
```

- [ ] **Step 4: Create postcss.config.mjs**

Create `admin/postcss.config.mjs`:

```javascript
const config = {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};

export default config;
```

- [ ] **Step 5: Create Dockerfile**

Create `admin/Dockerfile`:

```dockerfile
FROM node:20-slim

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

CMD ["npm", "run", "dev"]
```

- [ ] **Step 6: Create .env.local.example**

Create `admin/.env.local.example`:

```
NEXTAUTH_URL=http://localhost:3001
NEXTAUTH_SECRET=dev-secret-change-in-production
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
LINKEDIN_CLIENT_ID=
LINKEDIN_CLIENT_SECRET=
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
NEXT_PUBLIC_API_URL=http://localhost:8000
```

- [ ] **Step 7: Install dependencies**

```bash
cd admin && npm install
```

- [ ] **Step 8: Check Next.js 16 docs for breaking changes**

```bash
ls admin/node_modules/next/dist/docs/ 2>/dev/null || echo "No docs directory found"
```

If docs exist, read them and adjust the implementation accordingly.

- [ ] **Step 9: Commit**

```bash
git add admin/package.json admin/tsconfig.json admin/next.config.ts admin/postcss.config.mjs admin/Dockerfile admin/.env.local.example
# Do NOT commit node_modules — ensure admin/node_modules is in .gitignore
echo "node_modules/" >> admin/.gitignore 2>/dev/null
echo ".next/" >> admin/.gitignore 2>/dev/null
echo ".env.local" >> admin/.gitignore 2>/dev/null
git add admin/.gitignore
git commit -m "feat: scaffold admin Next.js app with config files"
```

---

### Task 11: Admin Auth + Layout + Sidebar

**Files:**
- Create: `admin/types/next-auth.d.ts`
- Create: `admin/lib/auth.ts`
- Create: `admin/app/api/auth/[...nextauth]/route.ts`
- Create: `admin/app/globals.css`
- Create: `admin/app/providers.tsx`
- Create: `admin/app/layout.tsx`
- Create: `admin/components/Sidebar.tsx`
- Create: `admin/components/AccessDenied.tsx`

- [ ] **Step 1: Create NextAuth type augmentations**

Create `admin/types/next-auth.d.ts`:

```typescript
import "next-auth";
import "next-auth/jwt";

declare module "next-auth" {
  interface Session {
    backendToken?: string;
    role?: string;
    backendUserId?: string;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    backendToken?: string;
    backendUserId?: string;
    backendRole?: string;
    provider?: string;
    providerId?: string;
  }
}
```

- [ ] **Step 2: Create auth config**

Create `admin/lib/auth.ts`:

```typescript
import type { NextAuthOptions } from "next-auth";
import GoogleProvider from "next-auth/providers/google";
import LinkedInProvider from "next-auth/providers/linkedin";
import GitHubProvider from "next-auth/providers/github";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const authOptions: NextAuthOptions = {
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID || "",
      clientSecret: process.env.GOOGLE_CLIENT_SECRET || "",
    }),
    LinkedInProvider({
      clientId: process.env.LINKEDIN_CLIENT_ID || "",
      clientSecret: process.env.LINKEDIN_CLIENT_SECRET || "",
    }),
    GitHubProvider({
      clientId: process.env.GITHUB_CLIENT_ID || "",
      clientSecret: process.env.GITHUB_CLIENT_SECRET || "",
    }),
  ],
  callbacks: {
    async jwt({ token, account, profile }) {
      if (account && profile) {
        token.provider = account.provider;
        token.providerId = account.providerAccountId;

        // Exchange OAuth credentials for a backend JWT
        try {
          const res = await fetch(`${API_URL}/api/auth/token`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              email: token.email || profile.email,
              name: token.name || profile.name || "",
              provider: account.provider,
              provider_id: account.providerAccountId,
            }),
          });
          if (res.ok) {
            const data = await res.json();
            token.backendToken = data.token;
            token.backendUserId = data.user.id;
            token.backendRole = data.user.role;
          }
        } catch {
          // Backend unavailable — token will lack backend fields
        }
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user) {
        session.backendToken = token.backendToken;
        session.role = token.backendRole;
        session.backendUserId = token.backendUserId;
      }
      return session;
    },
  },
  secret: process.env.NEXTAUTH_SECRET,
};
```

- [ ] **Step 3: Create NextAuth route handler**

Create `admin/app/api/auth/[...nextauth]/route.ts`:

```typescript
import NextAuth from "next-auth";
import { authOptions } from "@/lib/auth";

const handler = NextAuth(authOptions);
export { handler as GET, handler as POST };
```

- [ ] **Step 4: Create globals.css**

Create `admin/app/globals.css`:

```css
@import "tailwindcss";

body {
  background-color: #030712;
  color: #ffffff;
}
```

- [ ] **Step 5: Create providers**

Create `admin/app/providers.tsx`:

```typescript
"use client";

import { SessionProvider } from "next-auth/react";

export function Providers({ children }: { children: React.ReactNode }) {
  return <SessionProvider>{children}</SessionProvider>;
}
```

- [ ] **Step 6: Create Sidebar component**

Create `admin/components/Sidebar.tsx`:

```typescript
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSession, signOut } from "next-auth/react";

const NAV_ITEMS = [
  { href: "/", label: "Triage" },
  { href: "/startups", label: "Startups" },
  { href: "/experts", label: "Experts" },
  { href: "/templates", label: "Templates" },
  { href: "/users", label: "Users" },
];

export function Sidebar() {
  const pathname = usePathname();
  const { data: session } = useSession();

  return (
    <aside className="fixed left-0 top-0 h-full w-56 bg-gray-950 border-r border-gray-800 flex flex-col">
      <div className="p-4 border-b border-gray-800">
        <h1 className="text-lg font-bold text-indigo-400">Acutal Admin</h1>
      </div>
      <nav className="flex-1 p-2 space-y-1">
        {NAV_ITEMS.map((item) => {
          const isActive =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`block px-3 py-2 rounded text-sm ${
                isActive
                  ? "bg-indigo-600 text-white"
                  : "text-gray-400 hover:text-white hover:bg-gray-800"
              }`}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="p-4 border-t border-gray-800">
        <p className="text-xs text-gray-500 truncate">{session?.user?.email}</p>
        <button
          onClick={() => signOut()}
          className="mt-2 text-xs text-gray-400 hover:text-white"
        >
          Sign out
        </button>
      </div>
    </aside>
  );
}
```

- [ ] **Step 7: Create AccessDenied component**

Create `admin/components/AccessDenied.tsx`:

```typescript
"use client";

import { signIn, signOut, useSession } from "next-auth/react";

export function AccessDenied() {
  const { data: session } = useSession();

  if (!session) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <h1 className="text-2xl font-bold mb-4">Acutal Admin</h1>
          <p className="text-gray-400 mb-6">Sign in to access the admin panel.</p>
          <button
            onClick={() => signIn()}
            className="px-6 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700"
          >
            Sign in
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="text-center">
        <h1 className="text-2xl font-bold mb-4">Access Denied</h1>
        <p className="text-gray-400 mb-2">
          Signed in as {session.user?.email}
        </p>
        <p className="text-gray-500 mb-6">
          You need superadmin privileges to access this panel.
        </p>
        <button
          onClick={() => signOut()}
          className="px-6 py-2 bg-gray-700 text-white rounded hover:bg-gray-600"
        >
          Sign out
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 8: Create root layout**

Create `admin/app/layout.tsx`:

```typescript
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Acutal Admin",
  description: "Superadmin panel for Acutal",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <Providers>
          {children}
        </Providers>
      </body>
    </html>
  );
}
```

- [ ] **Step 9: Verify build**

```bash
cd admin && npx tsc --noEmit
```

Expected: No TypeScript errors.

- [ ] **Step 10: Commit**

```bash
git add admin/types/ admin/lib/auth.ts admin/app/ admin/components/Sidebar.tsx admin/components/AccessDenied.tsx
git commit -m "feat: add admin auth, layout, sidebar, and access control"
```

---

### Task 12: Admin API Client + Types

**Files:**
- Create: `admin/lib/types.ts`
- Create: `admin/lib/api.ts`

- [ ] **Step 1: Create types**

Create `admin/lib/types.ts`:

```typescript
export interface Industry {
  id: string;
  name: string;
  slug: string;
}

export interface Skill {
  id: string;
  name: string;
  slug: string;
}

export interface PipelineStartup {
  id: string;
  name: string;
  slug: string;
  description: string;
  stage: string;
  status: string;
  created_at: string;
  industries: Industry[];
  assignment_count: number;
  dimensions_configured: boolean;
}

export interface StartupDetail {
  id: string;
  name: string;
  slug: string;
  description: string;
  website_url: string | null;
  stage: string;
  status: string;
  location_city: string | null;
  location_state: string | null;
  location_country: string;
}

export interface ExpertApplication {
  id: string;
  user_id: string;
  bio: string;
  years_experience: number;
  application_status: string;
  created_at: string;
}

export interface ApprovedExpert {
  id: string;
  user_id: string;
  bio: string;
  years_experience: number;
  application_status: string;
  industries: Industry[];
  skills: Skill[];
  created_at: string;
}

export interface Assignment {
  id: string;
  startup_id: string;
  expert_id: string;
  assigned_by: string;
  status: string;
  assigned_at: string;
  responded_at: string | null;
}

export interface Dimension {
  id: string;
  dimension_name: string;
  dimension_slug: string;
  weight: number;
  sort_order: number;
}

export interface DDTemplate {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  created_at: string;
  dimensions: Dimension[];
}

export interface AdminUser {
  id: string;
  email: string;
  name: string;
  role: string;
}

// Triage feed item — union of different item types
export type TriageItemType = "startup" | "expert_application" | "assignment";

export interface TriageItem {
  type: TriageItemType;
  id: string;
  timestamp: string;
  data: PipelineStartup | ExpertApplication | Assignment;
}
```

- [ ] **Step 2: Create API client**

Create `admin/lib/api.ts`:

```typescript
import type {
  AdminUser,
  ApprovedExpert,
  Assignment,
  DDTemplate,
  Dimension,
  ExpertApplication,
  PipelineStartup,
  StartupDetail,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function apiFetch<T>(path: string, token: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...options?.headers,
    },
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const adminApi = {
  // Startups
  getPipeline: (token: string) =>
    apiFetch<PipelineStartup[]>("/api/admin/startups/pipeline", token),

  updateStartup: (token: string, id: string, body: Record<string, unknown>) =>
    apiFetch<StartupDetail>(`/api/admin/startups/${id}`, token, {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  // Expert applications
  getApplications: (token: string) =>
    apiFetch<ExpertApplication[]>("/api/admin/experts/applications", token),

  approveExpert: (token: string, profileId: string) =>
    apiFetch<ExpertApplication>(`/api/admin/experts/${profileId}/approve`, token, {
      method: "PUT",
    }),

  rejectExpert: (token: string, profileId: string) =>
    apiFetch<ExpertApplication>(`/api/admin/experts/${profileId}/reject`, token, {
      method: "PUT",
    }),

  // Approved experts
  getApprovedExperts: (token: string) =>
    apiFetch<ApprovedExpert[]>("/api/admin/experts", token),

  // Assignments
  getAssignments: (token: string, startupId: string) =>
    apiFetch<Assignment[]>(`/api/admin/startups/${startupId}/assignments`, token),

  assignExpert: (token: string, startupId: string, expertId: string) =>
    apiFetch<Assignment>(`/api/admin/startups/${startupId}/assign-expert`, token, {
      method: "POST",
      body: JSON.stringify({ expert_id: expertId }),
    }),

  deleteAssignment: (token: string, assignmentId: string) =>
    apiFetch<void>(`/api/admin/assignments/${assignmentId}`, token, {
      method: "DELETE",
    }),

  // Templates
  getTemplates: (token: string) =>
    apiFetch<DDTemplate[]>("/api/admin/dd-templates", token),

  getTemplate: (token: string, id: string) =>
    apiFetch<DDTemplate>(`/api/admin/dd-templates/${id}`, token),

  createTemplate: (token: string, body: { name: string; description?: string; dimensions: { dimension_name: string; weight: number; sort_order: number }[] }) =>
    apiFetch<DDTemplate>("/api/admin/dd-templates", token, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  updateTemplate: (token: string, id: string, body: { name: string; description?: string; dimensions: { dimension_name: string; weight: number; sort_order: number }[] }) =>
    apiFetch<DDTemplate>(`/api/admin/dd-templates/${id}`, token, {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  deleteTemplate: (token: string, id: string) =>
    apiFetch<void>(`/api/admin/dd-templates/${id}`, token, {
      method: "DELETE",
    }),

  // Dimensions
  getDimensions: (token: string, startupId: string) =>
    apiFetch<Dimension[]>(`/api/admin/startups/${startupId}/dimensions`, token),

  applyTemplate: (token: string, startupId: string, templateId: string) =>
    apiFetch<{ template_id: string; dimensions: Dimension[] }>(
      `/api/admin/startups/${startupId}/apply-template`, token, {
        method: "POST",
        body: JSON.stringify({ template_id: templateId }),
      },
    ),

  updateDimensions: (token: string, startupId: string, dimensions: { dimension_name: string; weight: number; sort_order: number }[]) =>
    apiFetch<Dimension[]>(`/api/admin/startups/${startupId}/dimensions`, token, {
      method: "PUT",
      body: JSON.stringify({ dimensions }),
    }),

  // Users
  getUsers: (token: string, role?: string) =>
    apiFetch<AdminUser[]>(`/api/admin/users${role ? `?role=${role}` : ""}`, token),
};
```

- [ ] **Step 3: Commit**

```bash
git add admin/lib/types.ts admin/lib/api.ts
git commit -m "feat: add admin API client and TypeScript types"
```

---

### Task 13: Shared Components (StatusBadge + DataTable)

**Files:**
- Create: `admin/components/StatusBadge.tsx`
- Create: `admin/components/DataTable.tsx`

- [ ] **Step 1: Create StatusBadge**

Create `admin/components/StatusBadge.tsx`:

```typescript
const COLORS: Record<string, string> = {
  pending: "bg-yellow-900 text-yellow-300",
  approved: "bg-emerald-900 text-emerald-300",
  rejected: "bg-red-900 text-red-300",
  featured: "bg-indigo-900 text-indigo-300",
  accepted: "bg-emerald-900 text-emerald-300",
  declined: "bg-red-900 text-red-300",
};

export function StatusBadge({ status }: { status: string }) {
  const color = COLORS[status] || "bg-gray-800 text-gray-300";
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${color}`}>
      {status}
    </span>
  );
}
```

- [ ] **Step 2: Create DataTable**

Create `admin/components/DataTable.tsx`:

```typescript
"use client";

import { useState } from "react";

interface Column<T> {
  key: string;
  label: string;
  render?: (item: T) => React.ReactNode;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  keyField: string;
}

export function DataTable<T extends Record<string, unknown>>({
  columns,
  data,
  keyField,
}: DataTableProps<T>) {
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortAsc, setSortAsc] = useState(true);

  const sorted = [...data].sort((a, b) => {
    if (!sortKey) return 0;
    const aVal = String(a[sortKey] ?? "");
    const bVal = String(b[sortKey] ?? "");
    return sortAsc ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
  });

  function handleSort(key: string) {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(true);
    }
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-800">
            {columns.map((col) => (
              <th
                key={col.key}
                onClick={() => handleSort(col.key)}
                className="text-left px-3 py-2 text-gray-400 font-medium cursor-pointer hover:text-white"
              >
                {col.label}
                {sortKey === col.key && (sortAsc ? " ↑" : " ↓")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((item) => (
            <tr
              key={String(item[keyField])}
              className="border-b border-gray-900 hover:bg-gray-900/50"
            >
              {columns.map((col) => (
                <td key={col.key} className="px-3 py-2">
                  {col.render ? col.render(item) : String(item[col.key] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {data.length === 0 && (
        <p className="text-center text-gray-500 py-8">No data</p>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add admin/components/StatusBadge.tsx admin/components/DataTable.tsx
git commit -m "feat: add StatusBadge and DataTable shared components"
```

---

### Task 14: Triage Feed Page + TriageFeedCard

**Files:**
- Create: `admin/components/TriageFeedCard.tsx`
- Create: `admin/app/page.tsx`

- [ ] **Step 1: Create TriageFeedCard component**

Create `admin/components/TriageFeedCard.tsx`:

```typescript
"use client";

import Link from "next/link";
import { StatusBadge } from "./StatusBadge";
import type { TriageItem, PipelineStartup, ExpertApplication, Assignment } from "@/lib/types";

interface TriageFeedCardProps {
  item: TriageItem;
  onApproveStartup?: (id: string) => void;
  onRejectStartup?: (id: string) => void;
  onApproveExpert?: (id: string) => void;
  onRejectExpert?: (id: string) => void;
}

const TYPE_BADGES: Record<string, string> = {
  startup: "bg-blue-900 text-blue-300",
  expert_application: "bg-purple-900 text-purple-300",
  assignment: "bg-orange-900 text-orange-300",
};

const TYPE_LABELS: Record<string, string> = {
  startup: "Startup",
  expert_application: "Expert App",
  assignment: "Assignment",
};

export function TriageFeedCard({
  item,
  onApproveStartup,
  onRejectStartup,
  onApproveExpert,
  onRejectExpert,
}: TriageFeedCardProps) {
  const timeAgo = new Date(item.timestamp).toLocaleDateString();

  return (
    <div className="border border-gray-800 rounded-lg p-4 hover:border-gray-700">
      <div className="flex items-center gap-2 mb-2">
        <span className={`text-xs px-2 py-0.5 rounded font-medium ${TYPE_BADGES[item.type]}`}>
          {TYPE_LABELS[item.type]}
        </span>
        <span className="text-xs text-gray-500">{timeAgo}</span>
      </div>

      {item.type === "startup" && renderStartup(item.data as PipelineStartup, onApproveStartup, onRejectStartup)}
      {item.type === "expert_application" && renderExpert(item.data as ExpertApplication, onApproveExpert, onRejectExpert)}
      {item.type === "assignment" && renderAssignment(item.data as Assignment)}
    </div>
  );
}

function renderStartup(
  s: PipelineStartup,
  onApprove?: (id: string) => void,
  onReject?: (id: string) => void,
) {
  return (
    <div>
      <div className="flex items-center justify-between">
        <Link href={`/startups/${s.id}`} className="font-medium text-white hover:text-indigo-400">
          {s.name}
        </Link>
        <StatusBadge status={s.status} />
      </div>
      <p className="text-sm text-gray-400 mt-1 line-clamp-2">{s.description}</p>
      <div className="flex items-center gap-2 mt-2 text-xs text-gray-500">
        <span>{s.stage}</span>
        {s.industries.map((i) => (
          <span key={i.id} className="bg-gray-800 px-1.5 py-0.5 rounded">{i.name}</span>
        ))}
      </div>
      {s.status === "pending" && (
        <div className="flex gap-2 mt-3">
          <button
            onClick={() => onApprove?.(s.id)}
            className="px-3 py-1 text-xs bg-emerald-700 text-white rounded hover:bg-emerald-600"
          >
            Approve
          </button>
          <button
            onClick={() => onReject?.(s.id)}
            className="px-3 py-1 text-xs bg-red-700 text-white rounded hover:bg-red-600"
          >
            Reject
          </button>
        </div>
      )}
    </div>
  );
}

function renderExpert(
  e: ExpertApplication,
  onApprove?: (id: string) => void,
  onReject?: (id: string) => void,
) {
  return (
    <div>
      <div className="flex items-center justify-between">
        <Link href={`/experts/${e.id}`} className="font-medium text-white hover:text-indigo-400">
          Expert Application
        </Link>
        <StatusBadge status={e.application_status} />
      </div>
      <p className="text-sm text-gray-400 mt-1">{e.bio}</p>
      <p className="text-xs text-gray-500 mt-1">{e.years_experience} years experience</p>
      {e.application_status === "pending" && (
        <div className="flex gap-2 mt-3">
          <button
            onClick={() => onApprove?.(e.id)}
            className="px-3 py-1 text-xs bg-emerald-700 text-white rounded hover:bg-emerald-600"
          >
            Approve
          </button>
          <button
            onClick={() => onReject?.(e.id)}
            className="px-3 py-1 text-xs bg-red-700 text-white rounded hover:bg-red-600"
          >
            Reject
          </button>
        </div>
      )}
    </div>
  );
}

function renderAssignment(a: Assignment) {
  return (
    <div>
      <p className="text-sm text-gray-300">
        Assignment <StatusBadge status={a.status} />
      </p>
      <p className="text-xs text-gray-500 mt-1">
        Expert responded: {a.responded_at ? new Date(a.responded_at).toLocaleDateString() : "pending"}
      </p>
    </div>
  );
}
```

- [ ] **Step 2: Create triage feed page**

Create `admin/app/page.tsx`:

```typescript
"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { AccessDenied } from "@/components/AccessDenied";
import { Sidebar } from "@/components/Sidebar";
import { TriageFeedCard } from "@/components/TriageFeedCard";
import { adminApi } from "@/lib/api";
import type { TriageItem, PipelineStartup, ExpertApplication } from "@/lib/types";

type FilterTab = "all" | "startups" | "experts" | "assignments";

export default function TriagePage() {
  const { data: session, status } = useSession();
  const [items, setItems] = useState<TriageItem[]>([]);
  const [filter, setFilter] = useState<FilterTab>("all");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (session?.backendToken) {
      loadFeed();
    }
  }, [session?.backendToken]);

  async function loadFeed() {
    if (!session?.backendToken) return;
    setLoading(true);
    try {
      const [startups, applications] = await Promise.all([
        adminApi.getPipeline(session.backendToken),
        adminApi.getApplications(session.backendToken),
      ]);

      const feed: TriageItem[] = [
        ...startups.map((s): TriageItem => ({
          type: "startup",
          id: s.id,
          timestamp: s.created_at,
          data: s,
        })),
        ...applications.map((e): TriageItem => ({
          type: "expert_application",
          id: e.id,
          timestamp: e.created_at,
          data: e,
        })),
      ];

      feed.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
      setItems(feed);
    } catch (err) {
      console.error("Failed to load feed:", err);
    } finally {
      setLoading(false);
    }
  }

  if (status === "loading") return null;
  if (!session || session.role !== "superadmin") return <AccessDenied />;

  const filtered = filter === "all"
    ? items
    : items.filter((i) =>
        filter === "startups" ? i.type === "startup"
        : filter === "experts" ? i.type === "expert_application"
        : i.type === "assignment"
      );

  async function handleApproveStartup(id: string) {
    if (!session?.backendToken) return;
    await adminApi.updateStartup(session.backendToken, id, { status: "approved" });
    loadFeed();
  }

  async function handleRejectStartup(id: string) {
    if (!session?.backendToken) return;
    await adminApi.updateStartup(session.backendToken, id, { status: "rejected" });
    loadFeed();
  }

  async function handleApproveExpert(id: string) {
    if (!session?.backendToken) return;
    await adminApi.approveExpert(session.backendToken, id);
    loadFeed();
  }

  async function handleRejectExpert(id: string) {
    if (!session?.backendToken) return;
    await adminApi.rejectExpert(session.backendToken, id);
    loadFeed();
  }

  const tabs: { key: FilterTab; label: string }[] = [
    { key: "all", label: "All" },
    { key: "startups", label: "Startups" },
    { key: "experts", label: "Experts" },
    { key: "assignments", label: "Assignments" },
  ];

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-6">
        <h2 className="text-xl font-bold mb-4">Triage Feed</h2>
        <div className="flex gap-2 mb-4">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setFilter(tab.key)}
              className={`px-3 py-1 text-sm rounded ${
                filter === tab.key
                  ? "bg-indigo-600 text-white"
                  : "bg-gray-800 text-gray-400 hover:text-white"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
        {loading ? (
          <p className="text-gray-500">Loading...</p>
        ) : (
          <div className="space-y-3">
            {filtered.map((item) => (
              <TriageFeedCard
                key={`${item.type}-${item.id}`}
                item={item}
                onApproveStartup={handleApproveStartup}
                onRejectStartup={handleRejectStartup}
                onApproveExpert={handleApproveExpert}
                onRejectExpert={handleRejectExpert}
              />
            ))}
            {filtered.length === 0 && (
              <p className="text-gray-500 text-center py-8">No items to review</p>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add admin/components/TriageFeedCard.tsx admin/app/page.tsx
git commit -m "feat: add triage feed page with inline actions"
```

---

### Task 15: Startups Pages

**Files:**
- Create: `admin/app/startups/page.tsx`
- Create: `admin/components/StartupEditor.tsx`
- Create: `admin/app/startups/[id]/page.tsx`

- [ ] **Step 1: Create startups list page**

Create `admin/app/startups/page.tsx`:

```typescript
"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import Link from "next/link";
import { AccessDenied } from "@/components/AccessDenied";
import { Sidebar } from "@/components/Sidebar";
import { StatusBadge } from "@/components/StatusBadge";
import { DataTable } from "@/components/DataTable";
import { adminApi } from "@/lib/api";
import type { PipelineStartup } from "@/lib/types";

export default function StartupsPage() {
  const { data: session, status } = useSession();
  const [startups, setStartups] = useState<PipelineStartup[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (session?.backendToken) {
      adminApi.getPipeline(session.backendToken).then(setStartups).finally(() => setLoading(false));
    }
  }, [session?.backendToken]);

  if (status === "loading") return null;
  if (!session || session.role !== "superadmin") return <AccessDenied />;

  const columns = [
    {
      key: "name",
      label: "Name",
      render: (s: PipelineStartup) => (
        <Link href={`/startups/${s.id}`} className="text-indigo-400 hover:text-indigo-300">
          {s.name}
        </Link>
      ),
    },
    { key: "stage", label: "Stage" },
    {
      key: "status",
      label: "Status",
      render: (s: PipelineStartup) => <StatusBadge status={s.status} />,
    },
    { key: "assignment_count", label: "Assignments" },
    {
      key: "dimensions_configured",
      label: "Dimensions",
      render: (s: PipelineStartup) => (
        <span className={s.dimensions_configured ? "text-emerald-400" : "text-gray-500"}>
          {s.dimensions_configured ? "Yes" : "No"}
        </span>
      ),
    },
    { key: "created_at", label: "Created" },
  ];

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-6">
        <h2 className="text-xl font-bold mb-4">Startups</h2>
        {loading ? (
          <p className="text-gray-500">Loading...</p>
        ) : (
          <DataTable columns={columns} data={startups as unknown as Record<string, unknown>[]} keyField="id" />
        )}
      </main>
    </div>
  );
}
```

- [ ] **Step 2: Create StartupEditor component**

Create `admin/components/StartupEditor.tsx`:

```typescript
"use client";

import { useState } from "react";

interface StartupEditorProps {
  initial: {
    name: string;
    description: string;
    website_url: string | null;
    stage: string;
    status: string;
    location_city: string | null;
    location_state: string | null;
    location_country: string;
  };
  onSave: (data: Record<string, string>) => Promise<void>;
}

const STAGES = ["pre_seed", "seed", "series_a", "series_b", "series_c", "growth"];
const STATUSES = ["pending", "approved", "rejected", "featured"];

export function StartupEditor({ initial, onSave }: StartupEditorProps) {
  const [form, setForm] = useState({
    name: initial.name,
    description: initial.description,
    website_url: initial.website_url || "",
    stage: initial.stage,
    status: initial.status,
    location_city: initial.location_city || "",
    location_state: initial.location_state || "",
    location_country: initial.location_country,
  });
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await onSave(form);
    } finally {
      setSaving(false);
    }
  }

  function update(field: string, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-sm text-gray-400 mb-1">Name</label>
        <input
          value={form.name}
          onChange={(e) => update("name", e.target.value)}
          className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-white"
        />
      </div>
      <div>
        <label className="block text-sm text-gray-400 mb-1">Description</label>
        <textarea
          value={form.description}
          onChange={(e) => update("description", e.target.value)}
          rows={4}
          className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-white"
        />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm text-gray-400 mb-1">Stage</label>
          <select
            value={form.stage}
            onChange={(e) => update("stage", e.target.value)}
            className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-white"
          >
            {STAGES.map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-1">Status</label>
          <select
            value={form.status}
            onChange={(e) => update("status", e.target.value)}
            className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-white"
          >
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
      </div>
      <div>
        <label className="block text-sm text-gray-400 mb-1">Website URL</label>
        <input
          value={form.website_url}
          onChange={(e) => update("website_url", e.target.value)}
          className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-white"
        />
      </div>
      <div className="grid grid-cols-3 gap-4">
        <div>
          <label className="block text-sm text-gray-400 mb-1">City</label>
          <input
            value={form.location_city}
            onChange={(e) => update("location_city", e.target.value)}
            className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-white"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-1">State</label>
          <input
            value={form.location_state}
            onChange={(e) => update("location_state", e.target.value)}
            className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-white"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-1">Country</label>
          <input
            value={form.location_country}
            onChange={(e) => update("location_country", e.target.value)}
            className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-white"
          />
        </div>
      </div>
      <button
        type="submit"
        disabled={saving}
        className="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50"
      >
        {saving ? "Saving..." : "Save Changes"}
      </button>
    </form>
  );
}
```

- [ ] **Step 3: Create DimensionManager component**

Create `admin/components/DimensionManager.tsx`:

```typescript
"use client";

import { useState } from "react";
import type { DDTemplate, Dimension } from "@/lib/types";

interface DimensionManagerProps {
  dimensions: Dimension[];
  templates: DDTemplate[];
  onApplyTemplate: (templateId: string) => Promise<void>;
  onSaveDimensions: (dims: { dimension_name: string; weight: number; sort_order: number }[]) => Promise<void>;
}

export function DimensionManager({
  dimensions,
  templates,
  onApplyTemplate,
  onSaveDimensions,
}: DimensionManagerProps) {
  const [dims, setDims] = useState(
    dimensions.map((d) => ({
      dimension_name: d.dimension_name,
      weight: d.weight,
      sort_order: d.sort_order,
    }))
  );
  const [saving, setSaving] = useState(false);

  function addDimension() {
    setDims([...dims, { dimension_name: "", weight: 1.0, sort_order: dims.length }]);
  }

  function removeDimension(index: number) {
    setDims(dims.filter((_, i) => i !== index));
  }

  function updateDim(index: number, field: string, value: string | number) {
    setDims(dims.map((d, i) => (i === index ? { ...d, [field]: value } : d)));
  }

  async function handleSave() {
    setSaving(true);
    try {
      await onSaveDimensions(dims);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h3 className="text-lg font-medium">Dimensions</h3>
        <select
          onChange={async (e) => {
            if (e.target.value) {
              await onApplyTemplate(e.target.value);
              e.target.value = "";
            }
          }}
          className="bg-gray-900 border border-gray-700 rounded px-2 py-1 text-sm text-white"
        >
          <option value="">Apply template...</option>
          {templates.map((t) => (
            <option key={t.id} value={t.id}>{t.name}</option>
          ))}
        </select>
      </div>

      <div className="space-y-2">
        {dims.map((dim, i) => (
          <div key={i} className="flex items-center gap-2">
            <input
              value={dim.dimension_name}
              onChange={(e) => updateDim(i, "dimension_name", e.target.value)}
              placeholder="Dimension name"
              className="flex-1 bg-gray-900 border border-gray-700 rounded px-2 py-1 text-sm text-white"
            />
            <input
              type="number"
              step="0.1"
              value={dim.weight}
              onChange={(e) => updateDim(i, "weight", parseFloat(e.target.value) || 1.0)}
              className="w-20 bg-gray-900 border border-gray-700 rounded px-2 py-1 text-sm text-white"
            />
            <button
              onClick={() => removeDimension(i)}
              className="text-red-400 hover:text-red-300 text-sm"
            >
              Remove
            </button>
          </div>
        ))}
      </div>

      <div className="flex gap-2">
        <button
          onClick={addDimension}
          className="px-3 py-1 text-sm bg-gray-800 text-gray-300 rounded hover:bg-gray-700"
        >
          + Add Dimension
        </button>
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-3 py-1 text-sm bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50"
        >
          {saving ? "Saving..." : "Save Dimensions"}
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create ExpertPicker component**

Create `admin/components/ExpertPicker.tsx`:

```typescript
"use client";

import { useState } from "react";
import type { ApprovedExpert, Assignment } from "@/lib/types";

interface ExpertPickerProps {
  experts: ApprovedExpert[];
  assignments: Assignment[];
  onAssign: (expertId: string) => Promise<void>;
  onRemoveAssignment: (assignmentId: string) => Promise<void>;
}

export function ExpertPicker({
  experts,
  assignments,
  onAssign,
  onRemoveAssignment,
}: ExpertPickerProps) {
  const [search, setSearch] = useState("");
  const [assigning, setAssigning] = useState<string | null>(null);

  const assignedExpertIds = new Set(assignments.map((a) => a.expert_id));

  const filtered = experts.filter(
    (e) =>
      !assignedExpertIds.has(e.id) &&
      (e.bio.toLowerCase().includes(search.toLowerCase()) ||
        e.industries.some((i) => i.name.toLowerCase().includes(search.toLowerCase())) ||
        e.skills.some((s) => s.name.toLowerCase().includes(search.toLowerCase())))
  );

  async function handleAssign(expertId: string) {
    setAssigning(expertId);
    try {
      await onAssign(expertId);
    } finally {
      setAssigning(null);
    }
  }

  return (
    <div className="space-y-4">
      <h3 className="text-lg font-medium">Expert Assignments</h3>

      {assignments.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm text-gray-400">Assigned:</p>
          {assignments.map((a) => (
            <div key={a.id} className="flex items-center justify-between bg-gray-900 rounded px-3 py-2">
              <span className="text-sm">
                Expert {a.expert_id.slice(0, 8)}... —{" "}
                <span className={a.status === "accepted" ? "text-emerald-400" : a.status === "declined" ? "text-red-400" : "text-yellow-400"}>
                  {a.status}
                </span>
              </span>
              <button
                onClick={() => onRemoveAssignment(a.id)}
                className="text-xs text-red-400 hover:text-red-300"
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      )}

      <div>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search experts by industry, skill, or bio..."
          className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-white"
        />
      </div>

      <div className="space-y-2 max-h-64 overflow-y-auto">
        {filtered.map((e) => (
          <div key={e.id} className="flex items-center justify-between bg-gray-900/50 rounded px-3 py-2">
            <div className="flex-1">
              <p className="text-sm text-white">{e.bio.slice(0, 80)}{e.bio.length > 80 ? "..." : ""}</p>
              <div className="flex gap-1 mt-1 flex-wrap">
                {e.industries.map((i) => (
                  <span key={i.id} className="text-xs bg-blue-900 text-blue-300 px-1.5 py-0.5 rounded">{i.name}</span>
                ))}
                {e.skills.map((s) => (
                  <span key={s.id} className="text-xs bg-purple-900 text-purple-300 px-1.5 py-0.5 rounded">{s.name}</span>
                ))}
              </div>
            </div>
            <button
              onClick={() => handleAssign(e.id)}
              disabled={assigning === e.id}
              className="ml-3 px-3 py-1 text-xs bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50"
            >
              {assigning === e.id ? "..." : "Assign"}
            </button>
          </div>
        ))}
        {filtered.length === 0 && (
          <p className="text-sm text-gray-500 text-center py-4">No matching experts</p>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Create startup detail page**

Create `admin/app/startups/[id]/page.tsx`:

```typescript
"use client";

import { useEffect, useState, use } from "react";
import { useSession } from "next-auth/react";
import { AccessDenied } from "@/components/AccessDenied";
import { Sidebar } from "@/components/Sidebar";
import { StartupEditor } from "@/components/StartupEditor";
import { DimensionManager } from "@/components/DimensionManager";
import { ExpertPicker } from "@/components/ExpertPicker";
import { adminApi } from "@/lib/api";
import type { PipelineStartup, DDTemplate, Dimension, ApprovedExpert, Assignment } from "@/lib/types";

export default function StartupDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: session, status } = useSession();
  const [startup, setStartup] = useState<PipelineStartup | null>(null);
  const [dimensions, setDimensions] = useState<Dimension[]>([]);
  const [templates, setTemplates] = useState<DDTemplate[]>([]);
  const [experts, setExperts] = useState<ApprovedExpert[]>([]);
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (session?.backendToken) loadAll();
  }, [session?.backendToken, id]);

  async function loadAll() {
    if (!session?.backendToken) return;
    setLoading(true);
    try {
      const [pipeline, dims, tmpls, exps, assigns] = await Promise.all([
        adminApi.getPipeline(session.backendToken),
        adminApi.getDimensions(session.backendToken, id),
        adminApi.getTemplates(session.backendToken),
        adminApi.getApprovedExperts(session.backendToken),
        adminApi.getAssignments(session.backendToken, id),
      ]);
      setStartup(pipeline.find((s) => s.id === id) || null);
      setDimensions(dims);
      setTemplates(tmpls);
      setExperts(exps);
      setAssignments(assigns);
    } finally {
      setLoading(false);
    }
  }

  if (status === "loading") return null;
  if (!session || session.role !== "superadmin") return <AccessDenied />;

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-6">
        {loading || !startup ? (
          <p className="text-gray-500">Loading...</p>
        ) : (
          <div className="space-y-8">
            <h2 className="text-xl font-bold">{startup.name}</h2>

            <section>
              <h3 className="text-lg font-medium mb-3">Edit Startup</h3>
              <StartupEditor
                initial={{
                  name: startup.name,
                  description: startup.description,
                  website_url: null,
                  stage: startup.stage,
                  status: startup.status,
                  location_city: null,
                  location_state: null,
                  location_country: "US",
                }}
                onSave={async (data) => {
                  await adminApi.updateStartup(session.backendToken!, id, data);
                  loadAll();
                }}
              />
            </section>

            <hr className="border-gray-800" />

            <section>
              <DimensionManager
                dimensions={dimensions}
                templates={templates}
                onApplyTemplate={async (templateId) => {
                  const result = await adminApi.applyTemplate(session.backendToken!, id, templateId);
                  setDimensions(result.dimensions);
                }}
                onSaveDimensions={async (dims) => {
                  const result = await adminApi.updateDimensions(session.backendToken!, id, dims);
                  setDimensions(result);
                }}
              />
            </section>

            <hr className="border-gray-800" />

            <section>
              <ExpertPicker
                experts={experts}
                assignments={assignments}
                onAssign={async (expertId) => {
                  await adminApi.assignExpert(session.backendToken!, id, expertId);
                  loadAll();
                }}
                onRemoveAssignment={async (assignmentId) => {
                  await adminApi.deleteAssignment(session.backendToken!, assignmentId);
                  loadAll();
                }}
              />
            </section>
          </div>
        )}
      </main>
    </div>
  );
}
```

- [ ] **Step 6: Commit**

```bash
git add admin/app/startups/ admin/components/StartupEditor.tsx admin/components/DimensionManager.tsx admin/components/ExpertPicker.tsx
git commit -m "feat: add startups list and detail pages with editor, dimensions, and expert picker"
```

---

### Task 16: Experts Pages

**Files:**
- Create: `admin/app/experts/page.tsx`
- Create: `admin/app/experts/[id]/page.tsx`

- [ ] **Step 1: Create experts list page**

Create `admin/app/experts/page.tsx`:

```typescript
"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import Link from "next/link";
import { AccessDenied } from "@/components/AccessDenied";
import { Sidebar } from "@/components/Sidebar";
import { StatusBadge } from "@/components/StatusBadge";
import { adminApi } from "@/lib/api";
import type { ExpertApplication } from "@/lib/types";

export default function ExpertsPage() {
  const { data: session, status } = useSession();
  const [applications, setApplications] = useState<ExpertApplication[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (session?.backendToken) {
      adminApi.getApplications(session.backendToken).then(setApplications).finally(() => setLoading(false));
    }
  }, [session?.backendToken]);

  if (status === "loading") return null;
  if (!session || session.role !== "superadmin") return <AccessDenied />;

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-6">
        <h2 className="text-xl font-bold mb-4">Expert Applications</h2>
        {loading ? (
          <p className="text-gray-500">Loading...</p>
        ) : (
          <div className="space-y-3">
            {applications.map((app) => (
              <div key={app.id} className="border border-gray-800 rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <Link href={`/experts/${app.id}`} className="font-medium text-indigo-400 hover:text-indigo-300">
                    Application {app.id.slice(0, 8)}...
                  </Link>
                  <StatusBadge status={app.application_status} />
                </div>
                <p className="text-sm text-gray-400">{app.bio}</p>
                <p className="text-xs text-gray-500 mt-1">{app.years_experience} years experience</p>
                {app.application_status === "pending" && (
                  <div className="flex gap-2 mt-3">
                    <button
                      onClick={async () => {
                        await adminApi.approveExpert(session.backendToken!, app.id);
                        setApplications((prev) => prev.filter((a) => a.id !== app.id));
                      }}
                      className="px-3 py-1 text-xs bg-emerald-700 text-white rounded hover:bg-emerald-600"
                    >
                      Approve
                    </button>
                    <button
                      onClick={async () => {
                        await adminApi.rejectExpert(session.backendToken!, app.id);
                        setApplications((prev) => prev.filter((a) => a.id !== app.id));
                      }}
                      className="px-3 py-1 text-xs bg-red-700 text-white rounded hover:bg-red-600"
                    >
                      Reject
                    </button>
                  </div>
                )}
              </div>
            ))}
            {applications.length === 0 && (
              <p className="text-gray-500 text-center py-8">No pending applications</p>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
```

- [ ] **Step 2: Create expert detail page**

Create `admin/app/experts/[id]/page.tsx`:

```typescript
"use client";

import { useEffect, useState, use } from "react";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { AccessDenied } from "@/components/AccessDenied";
import { Sidebar } from "@/components/Sidebar";
import { StatusBadge } from "@/components/StatusBadge";
import { adminApi } from "@/lib/api";
import type { ExpertApplication } from "@/lib/types";

export default function ExpertDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: session, status } = useSession();
  const router = useRouter();
  const [application, setApplication] = useState<ExpertApplication | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (session?.backendToken) {
      adminApi.getApplications(session.backendToken).then((apps) => {
        setApplication(apps.find((a) => a.id === id) || null);
        setLoading(false);
      });
    }
  }, [session?.backendToken, id]);

  if (status === "loading") return null;
  if (!session || session.role !== "superadmin") return <AccessDenied />;

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-6">
        {loading ? (
          <p className="text-gray-500">Loading...</p>
        ) : !application ? (
          <p className="text-gray-500">Application not found</p>
        ) : (
          <div className="max-w-2xl">
            <div className="flex items-center gap-3 mb-6">
              <h2 className="text-xl font-bold">Expert Application</h2>
              <StatusBadge status={application.application_status} />
            </div>
            <div className="space-y-4">
              <div>
                <label className="text-sm text-gray-400">Bio</label>
                <p className="text-white mt-1">{application.bio}</p>
              </div>
              <div>
                <label className="text-sm text-gray-400">Years of Experience</label>
                <p className="text-white mt-1">{application.years_experience}</p>
              </div>
              <div>
                <label className="text-sm text-gray-400">Applied</label>
                <p className="text-white mt-1">{new Date(application.created_at).toLocaleDateString()}</p>
              </div>
            </div>
            {application.application_status === "pending" && (
              <div className="flex gap-3 mt-6">
                <button
                  onClick={async () => {
                    await adminApi.approveExpert(session.backendToken!, id);
                    router.push("/experts");
                  }}
                  className="px-4 py-2 bg-emerald-700 text-white rounded hover:bg-emerald-600"
                >
                  Approve
                </button>
                <button
                  onClick={async () => {
                    await adminApi.rejectExpert(session.backendToken!, id);
                    router.push("/experts");
                  }}
                  className="px-4 py-2 bg-red-700 text-white rounded hover:bg-red-600"
                >
                  Reject
                </button>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add admin/app/experts/
git commit -m "feat: add experts list and detail pages with approve/reject"
```

---

### Task 17: Templates Pages + TemplateEditor

**Files:**
- Create: `admin/components/TemplateEditor.tsx`
- Create: `admin/app/templates/page.tsx`
- Create: `admin/app/templates/new/page.tsx`
- Create: `admin/app/templates/[id]/page.tsx`

- [ ] **Step 1: Create TemplateEditor component**

Create `admin/components/TemplateEditor.tsx`:

```typescript
"use client";

import { useState } from "react";

interface DimForm {
  dimension_name: string;
  weight: number;
  sort_order: number;
}

interface TemplateEditorProps {
  initial?: { name: string; description: string; dimensions: DimForm[] };
  onSave: (data: { name: string; description: string; dimensions: DimForm[] }) => Promise<void>;
  onDelete?: () => Promise<void>;
}

export function TemplateEditor({ initial, onSave, onDelete }: TemplateEditorProps) {
  const [name, setName] = useState(initial?.name || "");
  const [description, setDescription] = useState(initial?.description || "");
  const [dims, setDims] = useState<DimForm[]>(
    initial?.dimensions || [{ dimension_name: "", weight: 1.0, sort_order: 0 }]
  );
  const [saving, setSaving] = useState(false);

  function addDim() {
    setDims([...dims, { dimension_name: "", weight: 1.0, sort_order: dims.length }]);
  }

  function removeDim(i: number) {
    setDims(dims.filter((_, idx) => idx !== i));
  }

  function updateDim(i: number, field: string, value: string | number) {
    setDims(dims.map((d, idx) => (idx === i ? { ...d, [field]: value } : d)));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await onSave({ name, description, dimensions: dims });
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4 max-w-2xl">
      <div>
        <label className="block text-sm text-gray-400 mb-1">Template Name</label>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-white"
        />
      </div>
      <div>
        <label className="block text-sm text-gray-400 mb-1">Description</label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={2}
          className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-white"
        />
      </div>
      <div>
        <label className="block text-sm text-gray-400 mb-2">Dimensions</label>
        <div className="space-y-2">
          {dims.map((dim, i) => (
            <div key={i} className="flex items-center gap-2">
              <input
                value={dim.dimension_name}
                onChange={(e) => updateDim(i, "dimension_name", e.target.value)}
                placeholder="Dimension name"
                required
                className="flex-1 bg-gray-900 border border-gray-700 rounded px-2 py-1 text-sm text-white"
              />
              <label className="text-xs text-gray-500">Weight:</label>
              <input
                type="number"
                step="0.1"
                value={dim.weight}
                onChange={(e) => updateDim(i, "weight", parseFloat(e.target.value) || 1.0)}
                className="w-20 bg-gray-900 border border-gray-700 rounded px-2 py-1 text-sm text-white"
              />
              <button type="button" onClick={() => removeDim(i)} className="text-red-400 hover:text-red-300 text-sm">
                Remove
              </button>
            </div>
          ))}
        </div>
        <button type="button" onClick={addDim} className="mt-2 text-sm text-indigo-400 hover:text-indigo-300">
          + Add Dimension
        </button>
      </div>
      <div className="flex gap-3">
        <button
          type="submit"
          disabled={saving}
          className="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50"
        >
          {saving ? "Saving..." : initial ? "Update Template" : "Create Template"}
        </button>
        {onDelete && (
          <button
            type="button"
            onClick={onDelete}
            className="px-4 py-2 bg-red-700 text-white rounded hover:bg-red-600"
          >
            Delete
          </button>
        )}
      </div>
    </form>
  );
}
```

- [ ] **Step 2: Create templates list page**

Create `admin/app/templates/page.tsx`:

```typescript
"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import Link from "next/link";
import { AccessDenied } from "@/components/AccessDenied";
import { Sidebar } from "@/components/Sidebar";
import { adminApi } from "@/lib/api";
import type { DDTemplate } from "@/lib/types";

export default function TemplatesPage() {
  const { data: session, status } = useSession();
  const [templates, setTemplates] = useState<DDTemplate[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (session?.backendToken) {
      adminApi.getTemplates(session.backendToken).then(setTemplates).finally(() => setLoading(false));
    }
  }, [session?.backendToken]);

  if (status === "loading") return null;
  if (!session || session.role !== "superadmin") return <AccessDenied />;

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold">DD Templates</h2>
          <Link
            href="/templates/new"
            className="px-3 py-1 text-sm bg-indigo-600 text-white rounded hover:bg-indigo-700"
          >
            + New Template
          </Link>
        </div>
        {loading ? (
          <p className="text-gray-500">Loading...</p>
        ) : (
          <div className="space-y-3">
            {templates.map((t) => (
              <Link
                key={t.id}
                href={`/templates/${t.id}`}
                className="block border border-gray-800 rounded-lg p-4 hover:border-gray-700"
              >
                <h3 className="font-medium text-white">{t.name}</h3>
                {t.description && <p className="text-sm text-gray-400 mt-1">{t.description}</p>}
                <p className="text-xs text-gray-500 mt-1">{t.dimensions.length} dimensions</p>
              </Link>
            ))}
            {templates.length === 0 && (
              <p className="text-gray-500 text-center py-8">No templates yet</p>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
```

- [ ] **Step 3: Create new template page**

Create `admin/app/templates/new/page.tsx`:

```typescript
"use client";

import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { AccessDenied } from "@/components/AccessDenied";
import { Sidebar } from "@/components/Sidebar";
import { TemplateEditor } from "@/components/TemplateEditor";
import { adminApi } from "@/lib/api";

export default function NewTemplatePage() {
  const { data: session, status } = useSession();
  const router = useRouter();

  if (status === "loading") return null;
  if (!session || session.role !== "superadmin") return <AccessDenied />;

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-6">
        <h2 className="text-xl font-bold mb-4">New Template</h2>
        <TemplateEditor
          onSave={async (data) => {
            await adminApi.createTemplate(session.backendToken!, data);
            router.push("/templates");
          }}
        />
      </main>
    </div>
  );
}
```

- [ ] **Step 4: Create template detail page**

Create `admin/app/templates/[id]/page.tsx`:

```typescript
"use client";

import { useEffect, useState, use } from "react";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { AccessDenied } from "@/components/AccessDenied";
import { Sidebar } from "@/components/Sidebar";
import { TemplateEditor } from "@/components/TemplateEditor";
import { adminApi } from "@/lib/api";
import type { DDTemplate } from "@/lib/types";

export default function TemplateDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: session, status } = useSession();
  const router = useRouter();
  const [template, setTemplate] = useState<DDTemplate | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (session?.backendToken) {
      adminApi.getTemplate(session.backendToken, id).then(setTemplate).finally(() => setLoading(false));
    }
  }, [session?.backendToken, id]);

  if (status === "loading") return null;
  if (!session || session.role !== "superadmin") return <AccessDenied />;

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-6">
        {loading ? (
          <p className="text-gray-500">Loading...</p>
        ) : !template ? (
          <p className="text-gray-500">Template not found</p>
        ) : (
          <>
            <h2 className="text-xl font-bold mb-4">{template.name}</h2>
            <TemplateEditor
              initial={{
                name: template.name,
                description: template.description || "",
                dimensions: template.dimensions.map((d) => ({
                  dimension_name: d.dimension_name,
                  weight: d.weight,
                  sort_order: d.sort_order,
                })),
              }}
              onSave={async (data) => {
                await adminApi.updateTemplate(session.backendToken!, id, data);
                const updated = await adminApi.getTemplate(session.backendToken!, id);
                setTemplate(updated);
              }}
              onDelete={async () => {
                try {
                  await adminApi.deleteTemplate(session.backendToken!, id);
                  router.push("/templates");
                } catch {
                  alert("Cannot delete: template is in use by one or more startups.");
                }
              }}
            />
          </>
        )}
      </main>
    </div>
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add admin/components/TemplateEditor.tsx admin/app/templates/
git commit -m "feat: add templates list, create, and detail pages"
```

---

### Task 18: Users Page

**Files:**
- Create: `admin/app/users/page.tsx`

- [ ] **Step 1: Create users page**

Create `admin/app/users/page.tsx`:

```typescript
"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { AccessDenied } from "@/components/AccessDenied";
import { Sidebar } from "@/components/Sidebar";
import { DataTable } from "@/components/DataTable";
import { StatusBadge } from "@/components/StatusBadge";
import { adminApi } from "@/lib/api";
import type { AdminUser } from "@/lib/types";

const ROLES = ["all", "user", "expert", "superadmin"];

export default function UsersPage() {
  const { data: session, status } = useSession();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [roleFilter, setRoleFilter] = useState("all");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (session?.backendToken) {
      const role = roleFilter === "all" ? undefined : roleFilter;
      adminApi.getUsers(session.backendToken, role).then(setUsers).finally(() => setLoading(false));
    }
  }, [session?.backendToken, roleFilter]);

  if (status === "loading") return null;
  if (!session || session.role !== "superadmin") return <AccessDenied />;

  const columns = [
    { key: "email", label: "Email" },
    { key: "name", label: "Name" },
    {
      key: "role",
      label: "Role",
      render: (u: AdminUser) => <StatusBadge status={u.role} />,
    },
  ];

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-6">
        <h2 className="text-xl font-bold mb-4">Users</h2>
        <div className="flex gap-2 mb-4">
          {ROLES.map((r) => (
            <button
              key={r}
              onClick={() => { setRoleFilter(r); setLoading(true); }}
              className={`px-3 py-1 text-sm rounded ${
                roleFilter === r
                  ? "bg-indigo-600 text-white"
                  : "bg-gray-800 text-gray-400 hover:text-white"
              }`}
            >
              {r}
            </button>
          ))}
        </div>
        {loading ? (
          <p className="text-gray-500">Loading...</p>
        ) : (
          <DataTable columns={columns} data={users as unknown as Record<string, unknown>[]} keyField="id" />
        )}
      </main>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add admin/app/users/
git commit -m "feat: add users management page with role filter"
```

---

### Task 19: Verify Admin App Builds

- [ ] **Step 1: Check TypeScript compilation**

```bash
cd admin && npx tsc --noEmit
```

Fix any type errors found.

- [ ] **Step 2: Test dev server starts**

```bash
cd admin && npm run dev &
sleep 5
curl -s http://localhost:3001 | head -20
kill %1
```

Expected: HTML response from Next.js (may show sign-in page).

- [ ] **Step 3: Commit any fixes**

```bash
git add -A admin/
git commit -m "fix: resolve any TypeScript or build issues in admin app"
```

---

### Task 20: Docker Compose + CDK Update

**Files:**
- Modify: `docker-compose.yml`
- Modify: `infra/stacks/acutal_stack.py`

- [ ] **Step 1: Add admin service to docker-compose.yml**

Add the admin service after the frontend service in `docker-compose.yml`:

```yaml
  admin:
    build: ./admin
    ports:
      - "3001:3001"
    environment:
      NEXT_PUBLIC_API_URL: http://backend:8000
      NEXTAUTH_URL: http://localhost:3001
      NEXTAUTH_SECRET: dev-secret-change-in-production
    depends_on:
      - backend
    volumes:
      - ./admin:/app
      - /app/node_modules
    command: npm run dev
```

- [ ] **Step 2: Add admin Fargate service to CDK stack**

Add after the frontend service in `infra/stacks/acutal_stack.py`:

```python
        # Admin Service
        admin_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self, "AdminService",
            cluster=cluster,
            cpu=256,
            memory_limit_mib=512,
            desired_count=1,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_asset("../admin"),
                container_port=3001,
                environment={
                    "NEXT_PUBLIC_API_URL": f"http://{backend_service.load_balancer.load_balancer_dns_name}",
                    "NEXTAUTH_SECRET": "REPLACE_WITH_REAL_SECRET",
                },
            ),
        )
```

- [ ] **Step 3: Run full backend test suite**

```bash
cd backend && python -m pytest -v
```

Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml infra/stacks/acutal_stack.py
git commit -m "feat: add admin service to Docker Compose and CDK stack"
```

---

### Task 21: Seed DD Templates

**Files:**
- Create: `backend/app/db/seed_templates.py`

Seed the database with default DD templates so the admin panel has data to work with.

- [ ] **Step 1: Create seed script**

Create `backend/app/db/seed_templates.py`:

```python
"""Seed default due diligence templates."""
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.industry import Base
from app.models.template import DueDiligenceTemplate, TemplateDimension
from app.utils import slugify

TEMPLATES = {
    "SaaS": {
        "description": "Software-as-a-Service startup evaluation",
        "dimensions": [
            ("Market Size", 1.5),
            ("Product-Market Fit", 2.0),
            ("Revenue Model", 1.5),
            ("Technical Moat", 1.0),
            ("Team Strength", 1.5),
            ("Scalability", 1.0),
            ("Customer Acquisition", 1.0),
            ("Churn & Retention", 1.5),
        ],
    },
    "BioTech": {
        "description": "Biotech and life sciences startup evaluation",
        "dimensions": [
            ("Regulatory Path", 2.0),
            ("Clinical Pipeline", 2.0),
            ("IP Portfolio", 1.5),
            ("Market Size", 1.0),
            ("Team Credentials", 1.5),
            ("Funding Runway", 1.0),
            ("Scientific Validity", 2.0),
        ],
    },
    "FinTech": {
        "description": "Financial technology startup evaluation",
        "dimensions": [
            ("Regulatory Compliance", 2.0),
            ("Market Fit", 1.5),
            ("Security & Trust", 2.0),
            ("Unit Economics", 1.5),
            ("Scalability", 1.0),
            ("Team & Domain Expertise", 1.5),
            ("Competitive Landscape", 1.0),
        ],
    },
    "General": {
        "description": "General startup evaluation template",
        "dimensions": [
            ("Market Size", 1.0),
            ("Product-Market Fit", 1.5),
            ("Team Strength", 1.5),
            ("Business Model", 1.0),
            ("Competitive Advantage", 1.0),
            ("Traction", 1.0),
            ("Scalability", 1.0),
        ],
    },
}


async def seed_templates():
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        for name, config in TEMPLATES.items():
            template = DueDiligenceTemplate(
                name=name,
                slug=slugify(name),
                description=config["description"],
            )
            session.add(template)
            await session.flush()

            for i, (dim_name, weight) in enumerate(config["dimensions"]):
                session.add(TemplateDimension(
                    template_id=template.id,
                    dimension_name=dim_name,
                    dimension_slug=slugify(dim_name),
                    weight=weight,
                    sort_order=i,
                ))

        await session.commit()
        print(f"Seeded {len(TEMPLATES)} DD templates.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_templates())
```

- [ ] **Step 2: Run the seed script**

```bash
cd backend && python -m app.db.seed_templates
```

Expected: "Seeded 4 DD templates."

- [ ] **Step 3: Commit**

```bash
git add backend/app/db/seed_templates.py
git commit -m "feat: add DD template seed data (SaaS, BioTech, FinTech, General)"
```
