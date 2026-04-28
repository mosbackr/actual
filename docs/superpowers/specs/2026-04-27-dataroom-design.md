# Dataroom Design Spec

## Overview

Build a dataroom product where investors on Deep Thesis can request founders to upload structured due diligence documents. The investor sends a tokenized link to a founder's email with a personal message. The founder signs up/logs in, uploads documents across 6 standard sections (each with its own drag-and-drop zone), and submits. On submit, the backend runs the existing pitch analysis pipeline plus section-specific AI reviews and any custom evaluation criteria the investor defined. The investor receives in-app and email notifications when analysis completes, and views results on a dedicated datarooms page.

## Data Model

### `dataroom_requests` table

| Column | Type | Purpose |
|--------|------|---------|
| `id` | UUID PK | Primary key |
| `investor_id` | FK → users | The investor who created the request |
| `founder_id` | FK → users, nullable | Set when founder claims the request |
| `founder_email` | String(300) | Where to send the link |
| `founder_name` | String(300), nullable | Optional name for personalization |
| `company_name` | String(300), nullable | If investor knows the company name |
| `personal_message` | Text, nullable | Investor's custom message |
| `share_token` | String(64), unique | Token for the founder-facing link |
| `status` | Enum | `pending`, `uploading`, `submitted`, `analyzing`, `complete`, `expired` |
| `analysis_id` | FK → pitch_analyses, nullable | Set when analysis is triggered on submit |
| `custom_criteria` | JSONB, nullable | Array of `{description: str}` — investor-defined evaluation criteria |
| `created_at` | DateTime(tz) | Record creation |
| `expires_at` | DateTime(tz), nullable | Optional expiry for the link |

### `dataroom_documents` table

| Column | Type | Purpose |
|--------|------|---------|
| `id` | UUID PK | Primary key |
| `dataroom_request_id` | FK → dataroom_requests, CASCADE | |
| `section` | String(50) | `corporate`, `financials`, `fundraising`, `product`, `legal`, `team` |
| `original_filename` | String(500) | |
| `s3_key` | String(500) | |
| `file_type` | String(20) | pdf, docx, png, etc. |
| `file_size_bytes` | Integer | |
| `created_at` | DateTime(tz) | |

### `dataroom_section_reviews` table

| Column | Type | Purpose |
|--------|------|---------|
| `id` | UUID PK | Primary key |
| `dataroom_request_id` | FK → dataroom_requests, CASCADE | |
| `section` | String(50) | Which section (`corporate`, `financials`, etc.) or `custom` for custom criteria |
| `criteria_description` | Text, nullable | For custom criteria, the investor's description |
| `score` | Float, nullable | 0-100 |
| `summary` | Text, nullable | AI summary of section contents |
| `findings` | JSONB, nullable | Detailed findings |
| `status` | String(20) | `pending`, `complete`, `failed` |
| `created_at` | DateTime(tz) | |

### Enum: `DataroomStatus`

```python
class DataroomStatus(str, enum.Enum):
    pending = "pending"         # Link sent, founder hasn't started
    uploading = "uploading"     # Founder has uploaded at least one file
    submitted = "submitted"     # Founder clicked submit
    analyzing = "analyzing"     # Analysis pipeline running
    complete = "complete"       # Analysis done
    expired = "expired"         # Link expired
```

### Additions to existing models

- Add `dataroom_complete` to `NotificationType` enum
- Add `dataroom_submitted` to `NotificationType` enum

## Dataroom Sections

Six standard sections, each with its own drop zone:

| Section Key | Label | Expected Documents |
|-------------|-------|--------------------|
| `corporate` | Corporate Documents | Certificate of Incorporation, Bylaws, Cap Table, Operating Agreement |
| `financials` | Financials | P&L, Balance Sheet, Cash Flow, Projections, Bank Statements |
| `fundraising` | Fundraising | Pitch Deck, Executive Summary, Term Sheet, Use of Funds |
| `product` | Product | Demo, Screenshots, Technical Architecture, Roadmap |
| `legal` | Legal | IP Assignments, Material Contracts, Employment Agreements, Compliance |
| `team` | Team | Org Chart, Key Bios, Advisory Board, Compensation Summary |

Accepted file types: pdf, docx, doc, pptx, ppt, xlsx, xls, csv, png, jpg, jpeg, gif, webp, md, txt.

Max file size: 50MB per file. No limit on number of files per section.

## Flow

### Investor creates request

1. Investor navigates to `/datarooms`, clicks "Request Dataroom"
2. Fills in: founder email (required), founder name, company name, personal message
3. Optionally adds custom evaluation criteria — free-text descriptions of what to evaluate (e.g., "Evaluate the defensibility of their IP portfolio")
4. Clicks send → creates `DataroomRequest` with `pending` status, generates `share_token` via `secrets.token_urlsafe(32)`
5. Email sent to founder via Resend using `dataroom_request.html` template with investor's message + CTA link

### Founder uploads

1. Founder clicks link in email → `/dataroom/{share_token}`
2. Must be authenticated — redirect to signup/signin if not, with return URL back to the dataroom page
3. On first load, `founder_id` is set on the request if not already claimed
4. Sees 6 sections, each with drop zone and description of expected documents
5. Drags/browses files into each section — files upload immediately to S3, `DataroomDocument` records created
6. Status moves to `uploading` on first file upload
7. Can remove uploaded files, save progress, come back later
8. Clicks "Submit Dataroom" when done (requires at least one file uploaded)

### Analysis pipeline (on submit)

1. Status → `submitted` → `analyzing`
2. Create a `PitchAnalysis` record linked via `analysis_id`
3. All uploaded documents registered as `AnalysisDocument` records on that analysis
4. Run the existing pitch analysis pipeline — applicable phases only (claim extraction, fact check, scoring). Conversation analysis is skipped since dataroom uploads are documents, not meeting transcripts.
5. In parallel, run section-specific AI reviews — each section's documents evaluated with a section-appropriate prompt:
   - **Corporate**: Evaluates corporate structure, cap table health, governance
   - **Financials**: Analyzes revenue consistency, burn rate, projection assumptions, financial health
   - **Fundraising**: Assesses pitch clarity, fundraising strategy, valuation justification
   - **Product**: Reviews technical feasibility, product maturity, roadmap realism
   - **Legal**: Checks IP protection, contract risks, compliance status
   - **Team**: Evaluates founder backgrounds, team completeness, advisory strength
6. If investor added custom criteria, each one runs as an additional AI evaluation against all documents, stored as `DataroomSectionReview` with `section = "custom"` and `criteria_description` set
7. When everything completes, status → `complete`
8. Notify investor: in-app `dataroom_complete` notification + `dataroom_complete.html` email
9. Founder sees confirmation on the page immediately after clicking submit

### Investor views results

1. `/datarooms` — list of all requests with status badges
2. `/datarooms/[id]` — completed requests show pitch analysis results (reuse existing analysis view) plus "Section Reviews" tab with per-section scores, summaries, findings, and custom criteria evaluations

## API Endpoints

### Investor endpoints (auth required)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/datarooms` | POST | Create request (founder_email, personal_message, custom_criteria, etc.) |
| `/api/datarooms` | GET | List investor's dataroom requests with status |
| `/api/datarooms/{id}` | GET | Get request details + section reviews + analysis link |
| `/api/datarooms/{id}` | DELETE | Cancel/delete a request |

### Founder endpoints (auth required + token validation)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/datarooms/request/{share_token}` | GET | Get request info (sections, investor message) |
| `/api/datarooms/request/{share_token}/upload` | POST | Upload files to a section (multipart, `section` in form data) |
| `/api/datarooms/request/{share_token}/documents` | GET | List uploaded documents by section |
| `/api/datarooms/request/{share_token}/documents/{doc_id}` | DELETE | Remove an uploaded file |
| `/api/datarooms/request/{share_token}/submit` | POST | Submit dataroom, triggers analysis |

### Subscription gating

The `POST /api/datarooms` endpoint checks the investor's subscription tier for active request limits:
- Starter: 3 active requests
- Professional: 10 active requests
- Unlimited: no limit

Active = status not in (`complete`, `expired`).

## Notifications & Email

### New notification types

- `dataroom_submitted` — investor notified when founder submits
- `dataroom_complete` — investor notified when analysis finishes

### New email templates

1. **`dataroom_request.html`** — Sent to founder
   - Investor's personal message in a styled callout
   - CTA: "Upload Your Dataroom" → `{frontend_url}/dataroom/{share_token}`
   - Includes investor name and company name if provided

2. **`dataroom_submitted.html`** — Sent to investor when founder submits
   - "[Founder name] has submitted their dataroom for [Company]"
   - CTA: "View Dataroom" → `{frontend_url}/datarooms/{id}`

3. **`dataroom_complete.html`** — Sent to investor when analysis finishes
   - "The dataroom analysis for [Company] is ready"
   - CTA: "View Analysis" → `{frontend_url}/datarooms/{id}`

### In-app notifications

- On submit: `dataroom_submitted` notification for investor with link to `/datarooms/{id}`
- On complete: `dataroom_complete` notification for investor with link to `/datarooms/{id}`

### Founder confirmation

On submit, the page shows: "Thank you! Your dataroom has been shared with [investor name]." No email or in-app notification to the founder — they see the confirmation immediately on the page.

## Frontend Pages

### Investor pages

1. **`/datarooms`** — List page
   - Cards for each request: status badge, founder email, company name, date
   - "Request Dataroom" button opens modal with form fields
   - Completed datarooms link to detail page
   - Sidebar link: "Datarooms"

2. **`/datarooms/[id]`** — Detail page
   - Complete: pitch analysis results (reuse existing analysis view components) + "Section Reviews" tab with per-section scores/summaries + custom criteria evaluations
   - Analyzing: progress indicator
   - Pending/uploading: status info, founder email, documents uploaded so far

### Founder page

3. **`/dataroom/[token]`** — Upload experience (singular "dataroom")
   - Top: investor's personal message in styled callout
   - 6 sections, each with:
     - Section title and description of expected documents
     - Drag-and-drop zone (HTML5 native) + click to browse
     - List of uploaded files with remove button
   - Bottom: "Submit Dataroom" button (disabled until at least one file)
   - After submit: thank you message
   - Requires auth — redirect to signin with return URL

### Drag-and-drop implementation

Use native HTML5 drag-and-drop API with React state. No external library needed. Each section is an independent drop zone with `onDragOver`, `onDrop`, `onDragLeave` handlers. Files upload immediately on drop via the upload endpoint.

## Section-Specific AI Review Prompts

Each section review uses Claude to evaluate the uploaded documents with a tailored prompt:

- **Corporate**: "Evaluate the corporate structure, cap table health, and governance. Flag any red flags in equity distribution, vesting schedules, or corporate governance gaps."
- **Financials**: "Analyze the financial statements for revenue consistency, burn rate sustainability, and projection realism. Identify discrepancies between historical data and projections."
- **Fundraising**: "Assess the pitch and fundraising materials for clarity, compelling narrative, valuation justification, and use of funds specificity."
- **Product**: "Review technical architecture, product maturity, and roadmap feasibility. Assess the TRL level and identify technical risks."
- **Legal**: "Evaluate IP protection strength, identify material contract risks, check for compliance gaps, and flag any concerning employment agreement terms."
- **Team**: "Evaluate founder backgrounds against the company's domain, assess team completeness for the current stage, and evaluate advisory board relevance."

Custom criteria reviews use a generic prompt wrapper: "Evaluate the following dataroom documents against this specific criterion: {criteria_description}. Provide a score (0-100), summary, and detailed findings."

## S3 Key Structure

```
datarooms/{dataroom_request_id}/{section}/{uuid}/{filename}
```

## Startup Matching

When a founder submits and company_name is provided (either by investor or detected from documents), attempt to match against existing startups by name. If found, link the `PitchAnalysis.startup_id`. If not found, create a new startup record with `status=pending` and populate from the analysis enrichment.
