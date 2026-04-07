# Sub-project 1: Core Web App + Database + Auth/Roles

## Overview

Foundation layer for "Acutal" — a Rotten Tomatoes-style platform for evaluating startup investment opportunities. This sub-project establishes the database, authentication, API, frontend shell, and infrastructure that all subsequent sub-projects build on.

**Core thesis:** Investor momentum is noise. Domain expertise and startup fundamentals are the real signal. The platform surfaces AI-generated scores as a skeptical first pass, expert reviews as the authoritative signal, and user reviews as community sentiment — always showing the divergence between them.

## Sub-project Roadmap

1. **Core web app + database + auth/roles** (this spec)
2. Admin panel
3. Data ingestion pipeline
4. AI scoring engine
5. Expert review system
6. User review system

Each sub-project gets its own spec, plan, and implementation cycle.

## Tech Stack

- **Frontend:** Next.js (App Router), TypeScript, Tailwind CSS
- **Backend:** FastAPI (Python)
- **Database:** PostgreSQL on AWS RDS
- **Auth:** NextAuth.js (Google, LinkedIn, GitHub OAuth) + JWT validation in FastAPI
- **ORM/Migrations:** SQLAlchemy + Alembic
- **Infra:** AWS (ECS Fargate, RDS, S3, CloudFront, Secrets Manager)
- **Local dev:** Docker Compose

## Database Schema

### users
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| email | VARCHAR | unique |
| name | VARCHAR | |
| avatar_url | VARCHAR | nullable |
| auth_provider | ENUM(google, linkedin, github) | |
| provider_id | VARCHAR | provider-specific user ID |
| role | ENUM(user, expert, superadmin) | default: user |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

### expert_profiles
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| user_id | UUID | FK -> users, unique |
| bio | TEXT | |
| years_experience | INTEGER | |
| application_status | ENUM(pending, approved, rejected) | |
| approved_by | UUID | FK -> users, nullable |
| approved_at | TIMESTAMP | nullable |
| created_at | TIMESTAMP | |

### expert_industries
| Column | Type | Notes |
|--------|------|-------|
| expert_id | UUID | FK -> expert_profiles |
| industry_id | UUID | FK -> industries |

### expert_skills
| Column | Type | Notes |
|--------|------|-------|
| expert_id | UUID | FK -> expert_profiles |
| skill_id | UUID | FK -> skills |

### industries
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| name | VARCHAR | unique |
| slug | VARCHAR | unique |

### skills
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| name | VARCHAR | unique (go-to-market, technical architecture, regulatory compliance, etc.) |
| slug | VARCHAR | unique |

### startups
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| name | VARCHAR | |
| slug | VARCHAR | unique |
| description | TEXT | |
| website_url | VARCHAR | nullable |
| logo_url | VARCHAR | nullable |
| stage | ENUM(pre_seed, seed, series_a, series_b, series_c, growth) | |
| status | ENUM(pending, approved, rejected, featured) | default: pending |
| location_city | VARCHAR | nullable |
| location_state | VARCHAR | nullable |
| location_country | VARCHAR | default: US |
| founded_date | DATE | nullable |
| ai_score | FLOAT | nullable, composite score (0-100 scale) |
| expert_score | FLOAT | nullable, aggregate of expert reviews (0-100 scale) |
| user_score | FLOAT | nullable, aggregate of user reviews (0-100 scale) |
| search_vector | TSVECTOR | full-text search on name + description |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

### startup_industries
| Column | Type | Notes |
|--------|------|-------|
| startup_id | UUID | FK -> startups |
| industry_id | UUID | FK -> industries |

### startup_media
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| startup_id | UUID | FK -> startups |
| url | VARCHAR | |
| title | VARCHAR | |
| source | VARCHAR | (TechCrunch, LinkedIn, etc.) |
| media_type | ENUM(article, linkedin_post, video, podcast) | |
| published_at | TIMESTAMP | nullable |
| created_at | TIMESTAMP | |

### startup_scores_history
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| startup_id | UUID | FK -> startups |
| score_type | ENUM(ai, expert_aggregate, user_aggregate) | |
| score_value | FLOAT | |
| dimensions_json | JSONB | breakdown per scoring dimension |
| recorded_at | TIMESTAMP | snapshot timestamp |

## Auth & Roles

### OAuth Flow
1. NextAuth.js handles Google, LinkedIn, and GitHub OAuth on the frontend
2. On first login, a user record is created with role `user`
3. NextAuth issues a JWT containing user id, email, and role
4. FastAPI validates that JWT on every request using a shared secret/JWKS

### Roles
- **visitor** — unauthenticated. Read-only access to all public pages
- **user** — authenticated. Can browse, comment, review, and score startups
- **expert** — user who applied and was approved by superadmin. Can write due diligence reviews and expert scores within qualified industries/skills
- **superadmin** — full control over pipeline, users, experts, content

### Expert Application Flow
1. Authenticated user fills out application form (bio, industry selections, skill selections, years of experience, supporting links)
2. Application creates an `expert_profiles` record with status `pending`
3. Superadmin reviews and approves/rejects in admin panel
4. On approval, user's role is updated to `expert`, industry and skill tags are confirmed

### API Authorization
- FastAPI dependency injection checks JWT and role on each endpoint
- Role-checking dependencies: `require_role("expert")`, `require_role("superadmin")`
- Expert endpoints additionally verify the expert's industry/skill tags match the startup being reviewed

## API Design

### Public Endpoints (no auth)
- `GET /api/startups` — paginated list with filters: stage, industry, search query, sort by (ai_score, expert_score, user_score, newest)
- `GET /api/startups/{slug}` — full detail: description, media, current scores, score history, industry tags
- `GET /api/startups/{slug}/reviews` — expert reviews and user reviews as separate collections
- `GET /api/industries` — list all industries
- `GET /api/stages` — list all stages

### User Endpoints (require auth)
- `POST /api/startups/{slug}/reviews` — submit a user review (comment + score)
- `PUT /api/reviews/{id}` — edit own review
- `DELETE /api/reviews/{id}` — delete own review
- `GET /api/me` — current user profile
- `POST /api/experts/apply` — submit expert application

### Expert Endpoints (require expert role + domain match)
- `POST /api/startups/{slug}/expert-reviews` — submit structured due diligence review (scores per dimension + commentary per dimension)
- `PUT /api/expert-reviews/{id}` — edit own expert review
- `GET /api/expert/applications/mine` — check application status

### Auth Notes
- Auth itself handled by NextAuth on the frontend; FastAPI validates JWTs
- Users are matched by email across OAuth providers. If a user signs in with Google and later tries LinkedIn with the same email, they link to the same account. First provider used becomes the primary; subsequent providers are recognized by email match.

### Superadmin Endpoints (require superadmin role)
- `GET /api/admin/startups/pipeline` — pending startups for review
- `PUT /api/admin/startups/{id}` — approve/reject/enrich/feature a startup
- `GET /api/admin/experts/applications` — pending expert applications
- `PUT /api/admin/experts/{id}/approve` — approve expert
- `PUT /api/admin/experts/{id}/reject` — reject expert
- `GET /api/admin/users` — user management

### Search
- Full-text search on startup name + description via PostgreSQL `tsvector`/`tsquery`
- Industry and stage filtering via query params on the list endpoint

## Frontend Architecture

### Pages
- `/` — Homepage. Search bar + filters (stage, industry). Grid of startup evaluation cards sorted by newest/score. Each card shows: name, logo, one-line description, industry tags, stage badge, AI score, expert score, user score.
- `/startups/[slug]` — Startup detail page:
  - Hero: name, logo, website link, description, stage, industry tags
  - Score overview: AI score, expert aggregate, user aggregate with visual divergence indicator
  - Timeline chart: composite scores over time (AI, expert, user as separate lines)
  - Dimension breakdown: radar/spider chart showing per-dimension scores with AI vs expert vs user overlays
  - Media: linked articles, LinkedIn posts, videos
  - Expert reviews: structured due diligence reviews with per-dimension scores and commentary, reviewer credentials shown
  - User reviews: community reviews and scores, separate section
- `/experts/apply` — Expert application form
- `/profile` — User's own profile, reviews, application status
- `/admin` — Superadmin panel (sub-project 2)

### Components
- `StartupCard` — evaluation card for grid views
- `ScoreBadge` — score display with color coding (red/yellow/green)
- `ScoreComparison` — side-by-side expert vs user score display
- `ScoreTimeline` — line chart for historical scores (Recharts)
- `DimensionRadar` — radar chart for per-dimension breakdown (Recharts)
- `ReviewCard` — single review display (expert and user variants)
- `FilterBar` — stage, industry, search, sort controls

### UX Principles
- Startup cards are the primary browse experience — scannable, information-dense
- Expert vs user score split is always visible, never hidden
- Expert reviews show reviewer's credentials (industry, skills, years of experience)
- Search and tag filtering are prominent, not buried

## Infrastructure

### AWS Services
- **Frontend:** Next.js on ECS Fargate
- **Backend:** FastAPI on ECS Fargate
- **Database:** PostgreSQL on RDS (db.t3.micro initially)
- **Secrets:** AWS Secrets Manager for OAuth client secrets, JWT signing keys
- **Static assets:** S3 + CloudFront for logos, images

### Project Structure
```
acutal/
├── frontend/              # Next.js app
│   ├── app/               # App Router pages
│   ├── components/        # React components
│   ├── lib/               # API client, auth helpers
│   └── ...
├── backend/               # FastAPI app
│   ├── app/
│   │   ├── api/           # Route handlers
│   │   ├── models/        # SQLAlchemy models
│   │   ├── schemas/       # Pydantic schemas
│   │   ├── services/      # Business logic
│   │   ├── auth/          # JWT validation, role checks
│   │   └── db/            # Database connection, migrations
│   ├── alembic/           # DB migrations
│   └── ...
├── infra/                 # AWS CDK or Terraform
├── docker-compose.yml     # Local dev
└── docs/
```

### Local Development
- Docker Compose: PostgreSQL, FastAPI (hot reload), Next.js (hot reload)
- Single `docker compose up` to run everything

## Scope Boundaries

**In scope for this sub-project:**
- Database schema and migrations for all tables listed above
- Auth flow (NextAuth + JWT validation in FastAPI)
- All API endpoints listed above (stubs for review endpoints — full implementation in sub-projects 5 and 6)
- Frontend pages: homepage with startup card grid, startup detail page, expert application page, profile page
- Filtering and search on the homepage
- Docker Compose for local dev
- Basic AWS infra setup (ECS, RDS, S3)

**Out of scope (future sub-projects):**
- Admin panel UI (sub-project 2)
- Crawlers and data ingestion (sub-project 3)
- AI scoring engine (sub-project 4)
- Full expert review forms and due diligence workflow (sub-project 5)
- User review forms and community features (sub-project 6)
