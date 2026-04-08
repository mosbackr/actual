# Sub-project 2: Admin Panel

## Overview

Superadmin panel for Acutal — a standalone Next.js app for reviewing startups before they go live, managing expert applications, enriching startup profiles, assigning experts to startups for due diligence, and configuring which due diligence dimensions apply to each startup.

The backend API endpoints from sub-project 1 provide basic admin CRUD. This sub-project adds the admin frontend, new backend endpoints for templates/assignments/dimensions, and the database tables to support them.

## Sub-project Roadmap

1. Core web app + database + auth/roles (completed)
2. **Admin panel (this spec)**
3. Data ingestion pipeline
4. AI scoring engine
5. Expert review system
6. User review system

## Tech Stack

- **Admin Frontend:** Next.js (App Router), TypeScript, Tailwind CSS v4
- **Backend:** FastAPI (Python) — extends existing backend
- **Database:** PostgreSQL (extends existing schema)
- **Auth:** NextAuth.js (same OAuth providers as main app) + JWT validation in FastAPI
- **ORM/Migrations:** SQLAlchemy + Alembic

## New Database Tables

### due_diligence_templates
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| name | VARCHAR | unique (e.g., "SaaS", "BioTech", "FinTech") |
| slug | VARCHAR | unique |
| description | TEXT | nullable |
| created_at | TIMESTAMP | |

### template_dimensions
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| template_id | UUID | FK -> due_diligence_templates, ON DELETE CASCADE |
| dimension_name | VARCHAR | (e.g., "Market Size", "Technical Moat") |
| dimension_slug | VARCHAR | |
| weight | FLOAT | default 1.0, used for weighted scoring |
| sort_order | INTEGER | display ordering |

### startup_assignments
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| startup_id | UUID | FK -> startups |
| expert_id | UUID | FK -> expert_profiles |
| assigned_by | UUID | FK -> users (the superadmin) |
| status | ENUM(pending, accepted, declined) | default: pending |
| assigned_at | TIMESTAMP | |
| responded_at | TIMESTAMP | nullable |

### startup_dimensions
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| startup_id | UUID | FK -> startups |
| dimension_name | VARCHAR | |
| dimension_slug | VARCHAR | |
| weight | FLOAT | default 1.0 |
| sort_order | INTEGER | |

### Modified: startups
| Column | Type | Notes |
|--------|------|-------|
| template_id | UUID | FK -> due_diligence_templates, nullable. Added column. |

## New Backend API Endpoints

### Due Diligence Template CRUD (superadmin)

- `GET /api/admin/dd-templates` — list all templates
- `POST /api/admin/dd-templates` — create template with dimensions in one request
  - Body: `{ name, description, dimensions: [{ dimension_name, weight, sort_order }] }`
- `GET /api/admin/dd-templates/{id}` — single template with its dimensions
- `PUT /api/admin/dd-templates/{id}` — update template name, description, and dimensions (full replace of dimensions array)
  - Body: `{ name, description, dimensions: [{ dimension_name, weight, sort_order }] }`
- `DELETE /api/admin/dd-templates/{id}` — delete template only if no startups reference it; returns 409 if in use

### Startup Dimension Management (superadmin)

- `POST /api/admin/startups/{id}/apply-template` — copies dimensions from a template into `startup_dimensions`, sets `template_id` on startup
  - Body: `{ template_id }`
- `PUT /api/admin/startups/{id}/dimensions` — direct edit of startup's dimensions (full replace)
  - Body: `{ dimensions: [{ dimension_name, weight, sort_order }] }`
- `GET /api/admin/startups/{id}/dimensions` — get startup's current dimensions

### Expert Assignment (superadmin)

- `POST /api/admin/startups/{id}/assign-expert` — assign expert to startup
  - Body: `{ expert_id }`
  - Creates `startup_assignments` record with status `pending`
- `GET /api/admin/startups/{id}/assignments` — list assignments for a startup
- `DELETE /api/admin/assignments/{id}` — remove an assignment
- `GET /api/admin/experts` — list approved experts with their industry/skill tags (for the assignment picker UI)

### Expert-Facing Assignment Endpoints (expert role)

- `GET /api/expert/assignments` — expert sees their pending/accepted assignments
- `PUT /api/expert/assignments/{id}/accept` — expert accepts assignment, sets status and responded_at
- `PUT /api/expert/assignments/{id}/decline` — expert declines assignment, sets status and responded_at

### Enhanced Existing Endpoints

- `GET /api/admin/startups/pipeline` — enriched response: includes industry tags, assignment count, whether dimensions are configured
- `GET /api/admin/users` — add optional `?role=` query param filter

## Admin App Frontend Architecture

### Standalone App

Separate Next.js app at `admin/` in the monorepo. Same stack as main frontend (Next.js, TypeScript, Tailwind CSS v4) but separate deployment, separate port (3001 locally).

### Auth

Reuses the same NextAuth config (Google/LinkedIn/GitHub OAuth). On login, the app checks the user's role via `GET /api/me` — if not `superadmin`, shows an access denied page. JWT passed to backend on all API calls via Authorization header.

### Pages

| Route | Purpose |
|-------|---------|
| `/` | Triage feed (landing page) |
| `/startups` | All startups with status filter tabs (pending/approved/rejected/featured) |
| `/startups/[id]` | Startup detail — edit fields, manage dimensions, assign experts |
| `/experts` | Expert applications list + approved experts directory |
| `/experts/[id]` | Expert profile detail — approve/reject, view credentials |
| `/templates` | DD template list + create new |
| `/templates/[id]` | Template detail — edit name/description, manage dimensions |
| `/users` | User list with role filter |

### Triage Feed (Homepage)

A single chronological stream mixing three item types:
- **New startups** (status: pending) — inline approve/reject buttons, link to detail for enrichment
- **Expert applications** (status: pending) — inline approve/reject, expandable to show bio/credentials
- **Expert assignment responses** (accepted/declined) — informational cards

Each item is a card with a type badge (Startup / Expert App / Assignment), timestamp, and inline action buttons. Filter tabs at the top: All | Startups | Experts | Assignments.

The feed is powered by client-side merging: the admin app fetches pending startups, pending expert applications, and recent assignment responses in parallel, then merges and sorts them by timestamp into a single stream.

### Key Components

- **TriageFeedCard** — polymorphic card with startup/expert/assignment variants, inline actions
- **StartupEditor** — form for enriching startup fields (name, description, website_url, stage, status, location_city, location_state, location_country)
- **DimensionManager** — reorderable list of dimensions with weight sliders, "Apply Template" dropdown to copy from a template, add/remove individual dimensions
- **ExpertPicker** — searchable list of approved experts filtered by matching industry/skill tags, with assign button
- **TemplateEditor** — template name/description form + dimension list CRUD (add, remove, reorder, set weights)
- **StatusBadge** — colored badge for startup status, expert application status, assignment status
- **DataTable** — reusable sortable/filterable table for users, startups, experts list pages

### Layout

Sidebar navigation (Triage, Startups, Experts, Templates, Users) + main content area. No public-facing pages — everything behind auth gate.

## Infrastructure

### Local Development

Add `admin` service to existing `docker-compose.yml`:
- Port 3001 (main frontend is 3000)
- Same Docker network as backend and frontend
- Same environment variables: `NEXTAUTH_SECRET`, OAuth client IDs/secrets, `BACKEND_URL`
- `NEXTAUTH_URL` set to `http://localhost:3001`

### AWS Deployment

Separate ECS Fargate service for the admin app, deployed via the same CDK stack:
- Separate task definition and service
- Behind the same ALB on a different subdomain (`admin.acutal.com`) or path prefix
- Same secrets from Secrets Manager
- Access restricted via security group or CloudFront rules (IP allowlist for admin access)

## Scope Boundaries

**In scope:**
- New database tables and Alembic migration
- All new backend API endpoints listed above
- Enhancement of existing admin endpoints
- Complete admin frontend app with all pages and components listed
- Docker Compose service for local dev
- AWS CDK additions for admin app deployment

**Out of scope:**
- Email/push notifications for expert assignments (expert checks assignments via their profile page or the expert-facing API)
- Audit logging of admin actions (future enhancement)
- Batch operations (approve multiple startups at once)
- Real-time updates / WebSocket for triage feed
