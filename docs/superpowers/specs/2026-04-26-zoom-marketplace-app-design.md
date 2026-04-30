# Zoom Marketplace App for Pitch Intelligence

## Goal

Build a Zoom Marketplace app that automatically imports cloud recordings into DeepThesis Pitch Intelligence. Users install the app from Zoom Marketplace, link their DeepThesis account, and all their Zoom cloud recordings appear in Pitch Intelligence ready for analysis.

## Scope

This is the full Zoom Marketplace app (not a URL-paste workaround). It includes OAuth with Zoom, webhook-based recording import, account linking via DeepThesis email/password login, and frontend integration.

---

## 1. Zoom App Registration & OAuth Flow

### Zoom Marketplace App

Register a "General App" on the Zoom Marketplace developer portal (marketplace.zoom.us). This provides a Client ID and Client Secret. Required scopes: `recording:read`, `user:read`.

### Install Flow

1. User finds the app on Zoom Marketplace or clicks "Connect Zoom" from DeepThesis profile page.
2. Zoom redirects to `https://deepthesis.org/api/zoom/oauth/callback` with an authorization code.
3. Backend exchanges the code for Zoom access + refresh tokens via `POST https://zoom.us/oauth/token`.
4. Backend stores tokens temporarily in the session (not yet linked to a user).
5. Backend redirects to `https://www.deepthesis.org/zoom/connect?code=<temp_code>` where `temp_code` is a short-lived code referencing the stored Zoom tokens.
6. Frontend shows a DeepThesis login form (email/password). If the user is already logged in, skips to step 8.
7. User logs in with their DeepThesis email/password.
8. Frontend calls `POST /api/zoom/link` with the temp code and the user's auth token.
9. Backend creates a `zoom_connections` row linking the Zoom account to the DeepThesis user.
10. User sees "Zoom connected successfully" confirmation.

### Token Management

Zoom access tokens expire every hour. The `zoom_client` service refreshes them automatically before making API calls, using the stored refresh token. Updated tokens are saved back to the `zoom_connections` table.

---

## 2. Webhook Handling & Recording Import

### Webhook Endpoint

`POST /api/zoom/webhook` — receives events from Zoom.

Zoom requires webhook URL validation during app setup. The endpoint must handle:
- `endpoint.url_validation` — respond with the `plainToken` hashed with the webhook secret to prove ownership.
- `recording.completed` — the main event for importing recordings.

### Recording Import Flow

When `recording.completed` fires:

1. Validate webhook signature using the app's webhook secret token.
2. Extract `account_id` from the payload.
3. Look up `zoom_connections` by `zoom_account_id` to find the linked DeepThesis user.
4. If no linked user found, log and discard (user unlinked or never linked).
5. Check for duplicate: query `pitch_sessions` for matching `zoom_meeting_id`. Skip if exists.
6. Create a new `PitchSession` with:
   - `user_id` from the zoom connection
   - `title` = meeting topic from the payload
   - `status = downloading`
   - `source = "zoom"`
   - `zoom_meeting_id` = meeting UUID from the payload
7. The pitch worker picks up the session (status=downloading, source=zoom).
8. Worker calls `zoom_client.download_recording()` which:
   - Refreshes the access token if needed
   - Downloads the audio-only file (`recording_type: "audio_only"`) from the Zoom download URL
   - Falls back to MP4 if no audio-only file available
9. Worker uploads to S3 at `pitch-intelligence/{session_id}/audio.m4a`.
10. Transitions to `transcribing` — existing Deepgram pipeline takes over.

### Recording File Selection

Zoom recordings contain multiple files (video, audio, chat, transcript). Priority:
1. `audio_only` — smallest, fastest to download
2. `shared_screen_with_speaker_view` or `speaker_view` MP4 — extract audio
3. Any available MP4 — extract audio as fallback

---

## 3. Frontend Changes

### Zoom Connect Page (`/zoom/connect`)

A dedicated page shown after Zoom OAuth redirect. Two states:

**Already logged into DeepThesis:** Shows "Linking your Zoom account..." spinner, auto-calls the link API, then shows success message with a link back to profile.

**Not logged in:** Shows a simple login form (email + password) styled consistently with the rest of the app. On successful login, links the accounts and shows success.

### Profile Page — Connected Apps Section

Add a "Connected Apps" section to the existing profile page:
- **Not connected:** "Connect Zoom" button that redirects to `https://zoom.us/oauth/authorize?client_id=...&redirect_uri=...&response_type=code`
- **Connected:** Shows "Zoom Connected" with the Zoom email/account info and a "Disconnect" button
- Disconnect calls `DELETE /api/zoom/connection`, removes tokens, and updates UI

### Pitch Intelligence List

Sessions with `source="zoom"` display a small "Zoom" badge next to the title. No other changes — they behave identically to any other session.

### Session Detail Page

No changes. The existing status flow (downloading → transcribing → labeling → analyzing → complete) handles Zoom recordings the same as any other source.

---

## 4. Data Model

### New Table: `zoom_connections`

| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK, default uuid4 |
| user_id | UUID | FK → users.id, unique, not null |
| zoom_account_id | string(255) | unique, not null |
| zoom_email | string(500) | nullable |
| access_token | text | not null |
| refresh_token | text | not null |
| token_expires_at | datetime(tz) | not null |
| created_at | datetime(tz) | server default now() |
| updated_at | datetime(tz) | server default now(), on update |

One Zoom account per DeepThesis user (unique constraint on `user_id`). One DeepThesis user per Zoom account (unique constraint on `zoom_account_id`).

### PitchSession Changes

Add two columns:
- `source`: String(50), nullable. Values: `"upload"`, `"transcript"`, `"video_url"`, `"zoom"`. Null for existing sessions (treated as "upload").
- `zoom_meeting_id`: String(255), nullable. Used for deduplication — prevents re-importing the same recording.

### Alembic Migration

Single migration that:
1. Creates `zoom_connections` table
2. Adds `source` and `zoom_meeting_id` columns to `pitch_sessions`

---

## 5. New Files

| File | Responsibility |
|------|---------------|
| `backend/app/models/zoom_connection.py` | SQLAlchemy model for `zoom_connections` table |
| `backend/app/api/zoom.py` | OAuth callback, webhook handler, link/unlink endpoints |
| `backend/app/services/zoom_client.py` | Token refresh, Zoom API calls, recording download |
| `frontend/app/zoom/connect/page.tsx` | Post-OAuth account linking page |
| `backend/alembic/versions/XXXX_add_zoom_connections.py` | Migration |

## 6. Modified Files

| File | Change |
|------|--------|
| `backend/app/main.py` | Register zoom router |
| `backend/app/config.py` | Add `zoom_client_id`, `zoom_client_secret`, `zoom_webhook_secret` settings |
| `backend/app/services/pitch_worker.py` | When `source="zoom"`, use `zoom_client.download_recording()` instead of yt-dlp |
| `backend/app/services/video_downloader.py` | No changes — only used for YouTube/Loom URLs |
| `backend/app/models/pitch_session.py` | Add `source` and `zoom_meeting_id` columns |
| `frontend/app/profile/page.tsx` | Add "Connected Apps" section with Zoom connect/disconnect |
| `frontend/app/pitch-intelligence/page.tsx` | Show Zoom badge on sessions with `source="zoom"` |
| `frontend/lib/api.ts` | Add Zoom API methods (link, unlink, get connection status) |

---

## 7. API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/zoom/oauth/callback` | Zoom OAuth redirect — exchanges code for tokens, redirects to frontend |
| POST | `/api/zoom/webhook` | Receives Zoom webhook events (recording.completed, url_validation) |
| POST | `/api/zoom/link` | Links Zoom tokens to authenticated DeepThesis user |
| GET | `/api/zoom/connection` | Returns current user's Zoom connection status |
| DELETE | `/api/zoom/connection` | Disconnects Zoom (deletes tokens) |

---

## 8. Environment Variables

Three new settings (with `ACUTAL_` prefix per existing convention):
- `ACUTAL_ZOOM_CLIENT_ID` — from Zoom Marketplace app
- `ACUTAL_ZOOM_CLIENT_SECRET` — from Zoom Marketplace app
- `ACUTAL_ZOOM_WEBHOOK_SECRET` — for validating incoming webhooks

---

## 9. Error Handling

- **Zoom tokens expired and refresh fails:** Mark the zoom_connection as invalid, skip recording import, surface "Reconnect Zoom" in the frontend.
- **Recording download fails:** Set PitchSession to failed with descriptive error. User can retry or delete.
- **Duplicate webhook:** Check `zoom_meeting_id` before creating session. Silently skip duplicates.
- **User unlinks Zoom while recordings are importing:** In-progress downloads continue (tokens still valid briefly). Future webhooks are discarded (no matching zoom_connection).
- **Webhook validation failure:** Return 401, log the attempt.
