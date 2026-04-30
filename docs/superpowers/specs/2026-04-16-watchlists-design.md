# Watchlists Feature Design

## Goal

Let authenticated users save startups to a personal watchlist for quick access. A bookmark icon in the top nav links to a dedicated watchlist page. Users can add/remove startups from both the listing grid and detail pages.

## Architecture

A new `user_watchlist` table, 4 API endpoints, and 3 frontend touchpoints (nav icon, listing cards, watchlist page). No background jobs or automated alerts — this is a save-and-organize feature only.

## Data Model

### Table: `user_watchlist`

| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK, default uuid4 |
| user_id | UUID | FK → users.id, NOT NULL, indexed |
| startup_id | UUID | FK → startups.id, NOT NULL |
| created_at | DateTime(tz) | server_default now(), indexed |

- Unique constraint on `(user_id, startup_id)`
- Cascade delete on both FKs (if user or startup is deleted, watchlist entry goes too)

### SQLAlchemy Model

File: `backend/app/models/watchlist.py`

```python
import uuid
from sqlalchemy import Column, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from app.models.industry import Base

class UserWatchlist(Base):
    __tablename__ = "user_watchlist"
    __table_args__ = (
        UniqueConstraint("user_id", "startup_id", name="uq_user_watchlist"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    startup_id = Column(UUID(as_uuid=True), ForeignKey("startups.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
```

### Alembic Migration

File: `backend/alembic/versions/<hash>_add_user_watchlist.py`

Creates the table with columns, unique constraint, and indexes.

## API Endpoints

All endpoints require Bearer token authentication. File: `backend/app/api/watchlist.py`

### GET /api/watchlist

Returns paginated list of watched startups with full startup data.

Query params: `page` (default 1), `per_page` (default 20, max 100)

Response:
```json
{
  "total": 12,
  "page": 1,
  "per_page": 20,
  "pages": 1,
  "items": [
    {
      "startup_id": "uuid",
      "watched_at": "2026-04-16T...",
      "startup": {
        "id": "uuid",
        "name": "...",
        "slug": "...",
        "tagline": "...",
        "description": "...",
        "stage": "seed",
        "ai_score": 72,
        "logo_url": "...",
        "industries": [{"name": "Fintech"}],
        "form_sources": ["pitch_analysis"]
      }
    }
  ]
}
```

Sorted by `created_at DESC` (most recently added first).

### POST /api/watchlist

Add a startup to watchlist.

Body: `{ "startup_id": "uuid" }`

Response: `{ "success": true }`

Errors:
- 404 if startup_id doesn't exist
- 409 if already watching

### DELETE /api/watchlist/{startup_id}

Remove a startup from watchlist.

Response: `{ "success": true }`

Errors:
- 404 if not in watchlist

### GET /api/watchlist/ids

Returns just the UUIDs of all watched startups for the current user. Used by the listing page to populate bookmark icons without fetching full startup data.

Response:
```json
{
  "ids": ["uuid1", "uuid2", "uuid3"]
}
```

No pagination — returns all IDs (expected to be <100 for most users).

## Frontend

### 1. Nav Bookmark Icon

File: `frontend/components/WatchlistIcon.tsx`

- Bookmark SVG icon in the top nav bar, positioned next to the NotificationBell
- Shows count badge (small number) when watchlist has items
- Fetches count from `/api/watchlist/ids` (uses length of returned array)
- Polls every 60 seconds (or just on mount — watchlist changes are user-initiated so stale count is fine)
- Clicking navigates to `/watchlist`
- Only renders when user is authenticated

### 2. Watch Toggle on Startup Cards

File: modify `frontend/app/startups/page.tsx`

- Small bookmark icon in the top-right corner of each startup card
- On page load, fetch `/api/watchlist/ids` to get Set of watched IDs
- Icon is filled if startup ID is in the set, outline if not
- Click toggles: POST to add, DELETE to remove
- Optimistic UI update (toggle immediately, revert on error)
- Only show bookmark icons when user is authenticated

### 3. Watch Toggle on Startup Detail Page

File: modify `frontend/app/startups/[slug]/page.tsx`

- Bookmark button in the hero section (near the startup name/tagline area)
- Fetches `/api/watchlist/ids` on mount to determine initial state
- Same toggle behavior as listing cards
- Since this is a server component, the watch button will be a client component island

### 4. Watchlist Page

File: `frontend/app/watchlist/page.tsx`

- Client component (needs auth token for API calls)
- Fetches `GET /api/watchlist` with pagination
- Displays startup cards in a grid matching the `/startups` layout (3 columns desktop, 2 tablet, 1 mobile)
- Each card shows: logo, name, tagline, stage badge, AI score, industries, and a remove button (filled bookmark that toggles to remove)
- Empty state: centered message "No startups in your watchlist yet" with a link to "/startups" to browse
- Pagination: same Previous/Next pattern as startups page

### 5. Navbar Integration

File: modify `frontend/components/Navbar.tsx` (or equivalent)

- Add WatchlistIcon component next to NotificationBell
- Only visible when authenticated

## Router Registration

File: modify `backend/app/main.py`

Add `from app.api import watchlist` and register router with `app.include_router(watchlist.router)`.

## File Summary

| Action | File |
|--------|------|
| Create | `backend/app/models/watchlist.py` |
| Create | `backend/alembic/versions/..._add_user_watchlist.py` |
| Create | `backend/app/api/watchlist.py` |
| Create | `frontend/app/watchlist/page.tsx` |
| Create | `frontend/components/WatchlistIcon.tsx` |
| Modify | `backend/app/main.py` (register router) |
| Modify | `frontend/app/startups/page.tsx` (add bookmark icons to cards) |
| Modify | `frontend/app/startups/[slug]/page.tsx` (add watch button) |
| Modify | `frontend/components/Navbar.tsx` or equivalent (add WatchlistIcon) |
| Modify | `frontend/lib/api.ts` (add watchlist API methods) |
| Modify | `frontend/lib/types.ts` (add watchlist types) |
