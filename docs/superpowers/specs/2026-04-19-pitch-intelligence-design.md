# Pitch Intelligence — Design Spec

**Date:** 2026-04-19
**Status:** Design approved, not yet implemented

## Overview

Pitch Intelligence is a standalone module that lets users upload recorded pitch meetings, get AI-powered analysis of the conversation, fact-check both founders and investors, and receive actionable coaching — all improving over time through distillation learning across accumulated pitches.

## Access

- Requires authentication + active paid subscription
- No free-tier access

## Core Flow

1. User uploads audio/video of a pitch meeting
2. Server transcribes with speaker diarization (Deepgram Nova-2)
3. User labels detected speakers (name + role: founder/investor/other)
4. System runs a 5-phase AI analysis pipeline
5. Results displayed progressively on a dedicated page
6. Aggregate data feeds benchmarking and distillation learning

## Participants

The system handles any combination of multiple founders pitching to one or more investors. Speaker diarization detects distinct speakers automatically; the user assigns names and roles after transcription.

## Data Model

### `pitch_session`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID, PK | |
| `user_id` | FK → users | |
| `startup_id` | FK → startups, nullable | Optional link for richer context |
| `title` | string | User-provided or auto-generated |
| `status` | enum | `uploading`, `transcribing`, `labeling`, `analyzing`, `complete`, `failed` |
| `file_url` | string | S3 path to uploaded file |
| `file_duration_seconds` | integer | |
| `transcript_raw` | JSONB | Deepgram response with speaker segments |
| `transcript_labeled` | JSONB | After user assigns names/roles |
| `scores` | JSONB | Overall + per-dimension scores |
| `benchmark_percentiles` | JSONB | Comparison against aggregate |
| `created_at` | timestamp | |
| `updated_at` | timestamp | |

### `pitch_analysis_result`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID, PK | |
| `session_id` | FK → pitch_session | |
| `phase` | enum | `claim_extraction`, `fact_check_founders`, `fact_check_investors`, `conversation_analysis`, `scoring`, `benchmark` |
| `status` | enum | `pending`, `running`, `complete`, `failed` |
| `result` | JSONB | Phase-specific structured output |
| `created_at` | timestamp | |
| `updated_at` | timestamp | |

### `pitch_benchmark`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID, PK | |
| `dimension` | string | e.g., "clarity", "financial_rigor", "q_and_a_handling" |
| `stage` | string, nullable | seed, series_a, etc. Null = cross-stage |
| `industry` | string, nullable | Null = cross-industry |
| `sample_count` | integer | |
| `mean_score` | float | |
| `median_score` | float | |
| `p25` | float | |
| `p75` | float | |
| `patterns` | JSONB | Distilled insights from pattern recognition |
| `updated_at` | timestamp | |

No changes to existing tables. The optional `startup_id` FK on `pitch_session` is the only connection to the current data model.

## AI Analysis Pipeline

Five phases, run sequentially (later phases depend on earlier outputs).

### Phase 1: Claim Extraction (Claude Sonnet)

- Input: labeled transcript
- Walks through the conversation and tags every factual claim by founders (revenue, growth rates, market size, user counts) and every piece of advice/assertion by investors (market opinions, valuation benchmarks, strategic suggestions)
- Output: structured list of claims with speaker attribution, timestamp, verbatim quote, and claim category

### Phase 2: Fact-Checking (Claude Sonnet + Perplexity)

- Input: extracted claims from Phase 1
- Two parallel sub-tasks:
  - **Founder fact-check**: verifies each founder claim against web data (market size, competitor numbers, industry stats)
  - **Investor fact-check**: verifies investor advice/assertions (are their comparisons accurate? is their market read correct? is their suggested strategy sound?)
- Output: per-claim verdict (`verified` / `disputed` / `unverifiable`) with sources and explanation

### Phase 3: Conversation Analysis (Claude Opus)

- Input: full labeled transcript + fact-check results
- Evaluates three dimensions:
  - **Presentation quality**: pacing, filler words, confidence, clarity of explanations, how well founders handled tough questions
  - **Meeting dynamics**: who dominated, investor engagement levels, tension points, defensive moments
  - **Strategic read**: investor interest signals, unvoiced concerns implied by questions, power dynamic shifts
- Output: structured assessment per dimension with specific transcript references

### Phase 4: Scoring & Recommendations (Claude Opus)

- Input: all prior phase outputs
- Dimensions scored 0-100: pitch clarity, financial rigor, Q&A handling, investor engagement, fact accuracy, overall pitch effectiveness
- Produces actionable recommendations ranked by impact, each tied to specific transcript moments
- Output: scores + prioritized improvement list

### Phase 5: Benchmark Comparison (deterministic, no AI)

- Input: scores from Phase 4 + `pitch_benchmark` table
- Compares this pitch against aggregate percentiles by stage/industry
- Updates aggregate stats in `pitch_benchmark` table
- Output: percentile rankings per dimension

## File Storage & Transcription

### Upload Flow

1. Frontend requests presigned S3 URL from backend (`POST /api/pitch-intelligence/upload`)
2. Frontend uploads directly to S3 (avoids proxying large files)
3. Frontend notifies backend on completion (`POST /api/pitch-intelligence/{id}/upload-complete`)
4. Backend triggers Deepgram transcription

### Transcription

- Deepgram Nova-2 with `diarize=true`, `smart_format=true`, `punctuate=true`
- Async processing via webhook or polling
- Result stored as `transcript_raw` JSONB
- Session status moves to `labeling` on completion

### File Lifecycle

- Original audio/video kept in S3 for 90 days, then auto-deleted via S3 lifecycle policy
- Transcripts persist indefinitely (small, needed for benchmarking)

### Accepted Formats

- Audio: MP3, WAV, M4A
- Video: MP4, WebM
- Max file size: 500MB (~2hr meetings)

### Cost Per Pitch

- Deepgram Nova-2: ~$0.0043/min (~$0.26 for a 60-min pitch)
- AI analysis phases: ~$0.50-1.50 depending on transcript length
- S3 storage: negligible

## API Endpoints

All endpoints require authentication + active subscription.

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/pitch-intelligence/upload` | Create session, return presigned S3 URL |
| `POST` | `/api/pitch-intelligence/{id}/upload-complete` | Trigger transcription |
| `GET` | `/api/pitch-intelligence/{id}` | Get session with all results |
| `PUT` | `/api/pitch-intelligence/{id}/speakers` | Submit speaker labels, trigger analysis |
| `GET` | `/api/pitch-intelligence/{id}/status` | Lightweight polling for phase progress |
| `GET` | `/api/pitch-intelligence` | List user's pitch sessions |
| `DELETE` | `/api/pitch-intelligence/{id}` | Delete session + S3 file |
| `GET` | `/api/pitch-intelligence/{id}/transcript` | Full labeled transcript |
| `GET` | `/api/pitch-intelligence/benchmarks` | Aggregate benchmark stats |

Processing runs in the `analysis_worker` container alongside existing startup analysis.

## Frontend

### Routes

- `/pitch-intelligence` — main page (upload + session list)
- `/pitch-intelligence/[id]` — results page

### Upload/List Page (`/pitch-intelligence`)

- Drag-and-drop upload zone or file picker
- Optional title field and startup link (typeahead search)
- List of previous pitch sessions with status, date, overall score

### Speaker Labeling State

- Shows after transcription completes
- Detected speakers listed as "Speaker 1", "Speaker 2", etc.
- Each speaker: short audio sample, name text field, role dropdown (Founder / Investor / Other)
- Preview transcript lines per speaker for identification
- "Start Analysis" button once all speakers labeled

### Results Page (`/pitch-intelligence/[id]`)

- **Header**: title, date, duration, linked startup, overall score badge
- **Transcript panel**: full transcript with speaker colors, clickable timestamps
- **Fact-Check section**: two tabs (Founder Claims / Investor Advice), each claim with verbatim quote, verdict badge, sources, explanation
- **Conversation Analysis section**: three subsections (Presentation Quality, Meeting Dynamics, Strategic Read) with clickable transcript references
- **Scores dashboard**: radar chart of dimension scores + percentile benchmark bars
- **Recommendations**: prioritized improvements tied to specific transcript moments
- **History sidebar** (if 2+ sessions): improvement tracking with sparkline charts

Progressive loading — sections appear as each phase completes, matching the existing analysis page pattern.

## Distillation Learning

Three layers, built incrementally.

### Layer 1: Benchmarking (from day one)

- After each pitch scores, update `pitch_benchmark` with running aggregates per dimension/stage/industry
- Percentile math, no AI needed
- Meaningful after ~20-30 pitches per cohort
- Frontend shows: "Your clarity score is in the 72nd percentile among seed-stage pitches"

### Layer 2: Pattern Recognition (after ~100+ pitches)

- Weekly batch job analyzes completed pitches for recurring patterns
- Claude processes clusters and identifies trends:
  - "Investors in healthtech consistently push back on regulatory timeline estimates"
  - "Founders who quantify their competitive moat score 30% higher on investor engagement"
- Stored in `patterns` JSONB on `pitch_benchmark`
- Surfaced as contextual insights on results pages

### Layer 3: Personalized Coaching (when user has 3+ pitches)

- Compare user's pitches over time for improvement tracking
- Targeted advice: "Your Q&A handling improved from 45 to 68 over your last 3 pitches. Your biggest remaining gap is financial rigor."
- Accessible from "My Progress" section

### Data Privacy

- Benchmarks and patterns are always aggregate — no individual transcripts leak across users
- Pattern extraction uses anonymized score/dimension data, not raw transcripts
- Users can opt out of contributing to benchmarks
