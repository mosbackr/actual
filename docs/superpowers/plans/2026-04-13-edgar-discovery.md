# EDGAR Company Discovery — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the EDGAR scraper to discover new venture-backed startups from SEC Form D filings, extract structured data, add them to the database, and auto-enrich with Perplexity.

**Architecture:** Four new step types (`discover_filings`, `extract_company`, `add_startup`, `enrich_startup`) added to the existing EdgarJob/EdgarJobStep system. A new `scan_mode="discover"` triggers a pipeline that searches EDGAR EFTS for Form D filings, filters by SIC code and amount, deduplicates against existing startups, creates new Startup records with EDGAR-sourced data, and enriches via Perplexity with location protection.

**Tech Stack:** Python/FastAPI, SQLAlchemy, EDGAR EFTS API, Perplexity Sonar Pro, Next.js/React admin frontend.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `backend/app/models/edgar_job.py` | Modify | Add 4 new `EdgarStepType` values, 4 new `EdgarJobPhase` values |
| `backend/app/services/edgar.py` | Modify | Add `search_form_d_filings()` EFTS function |
| `backend/app/services/edgar_processor.py` | Modify | Add SIC whitelist, entity name filter, stage inference, CIK extraction from EFTS hits |
| `backend/app/services/edgar_worker.py` | Modify | Add 4 new step executors, discovery worker preferences, discovery progress tracking |
| `backend/app/services/enrichment.py` | Modify | Add location protection for startups with `sec_cik` |
| `backend/app/api/admin_edgar.py` | Modify | Add `discover_days` to request, discover mode job creation, discovery log formatting |
| `admin/lib/api.ts` | Modify | Update `startEdgar` to pass `discover_days` |
| `admin/app/edgar/page.tsx` | Modify | Add "Discover New" button, days input, discovery progress cards |

---

### Task 1: Add New Enum Values to EdgarJob Model

**Files:**
- Modify: `backend/app/models/edgar_job.py`

- [ ] **Step 1: Add 4 new values to `EdgarStepType` enum**

In `backend/app/models/edgar_job.py`, add these values to `EdgarStepType` after `process_filing`:

```python
class EdgarStepType(str, enum.Enum):
    resolve_cik = "resolve_cik"
    fetch_filings = "fetch_filings"
    process_filing = "process_filing"
    discover_filings = "discover_filings"
    extract_company = "extract_company"
    add_startup = "add_startup"
    enrich_startup = "enrich_startup"
```

- [ ] **Step 2: Add 4 new values to `EdgarJobPhase` enum**

Add discovery phases after `complete`:

```python
class EdgarJobPhase(str, enum.Enum):
    resolving_ciks = "resolving_ciks"
    fetching_filings = "fetching_filings"
    processing_filings = "processing_filings"
    complete = "complete"
    discovering = "discovering"
    extracting = "extracting"
    adding = "adding"
    enriching = "enriching"
```

- [ ] **Step 3: Verify syntax**

Run: `python3 -m py_compile backend/app/models/edgar_job.py`
Expected: No output (success)

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/edgar_job.py
git commit -m "feat(edgar): add discovery step types and job phases to model enums"
```

---

### Task 2: Add EFTS Search Function to EDGAR Client

**Files:**
- Modify: `backend/app/services/edgar.py`

- [ ] **Step 1: Add `EdgarFormDHit` dataclass**

Add after the `EdgarFiling` dataclass at line 64:

```python
@dataclass
class EdgarFormDHit:
    """A Form D filing hit from EDGAR EFTS search."""
    accession_number: str
    entity_name: str
    file_date: str
    file_num: str | None
    cik: str | None
```

- [ ] **Step 2: Add `search_form_d_filings` function**

Add after `get_company_info()` at end of file:

```python
async def search_form_d_filings(
    start_date: str,
    end_date: str,
    page_from: int = 0,
    page_size: int = 100,
) -> tuple[list[EdgarFormDHit], int]:
    """Search EDGAR EFTS for Form D filings within a date range.

    Returns (hits, total_count). Caller paginates using page_from.
    """
    url = (
        f"https://efts.sec.gov/LATEST/search-index"
        f"?q=*&forms=D&dateRange=custom"
        f"&startdt={start_date}&enddt={end_date}"
        f"&from={page_from}&size={page_size}"
    )

    try:
        resp = await _rate_limited_get(url)
    except httpx.HTTPStatusError as e:
        logger.warning(f"EDGAR EFTS search failed: {e}")
        return [], 0

    data = resp.json()
    total = data.get("hits", {}).get("total", {}).get("value", 0)
    raw_hits = data.get("hits", {}).get("hits", [])

    hits = []
    for hit in raw_hits:
        source = hit.get("_source", {})
        accession = hit.get("_id", "")

        # Extract CIK from file_num (e.g., "021-12345") or from the filing URL
        display_names = source.get("display_names", [])
        entity_name = display_names[0] if display_names else ""
        file_date = source.get("file_date", "")
        file_num = source.get("file_num", "")

        # CIK is often in the entity_id or can be extracted from accession path
        entity_id = source.get("entity_id", "")
        cik = entity_id if entity_id else None

        hits.append(EdgarFormDHit(
            accession_number=accession,
            entity_name=entity_name,
            file_date=file_date,
            file_num=file_num,
            cik=cik,
        ))

    return hits, total
```

- [ ] **Step 3: Add `get_cik_from_accession` function**

For hits where CIK is not embedded, we look it up:

```python
async def get_cik_from_accession(accession_number: str) -> str | None:
    """Resolve CIK from an accession number using the EDGAR filing index."""
    accession_path = accession_number.replace("-", "")
    url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&filenum={accession_number}&type=D&dateb=&owner=include&count=1&search_text=&action=getcompany&output=atom"

    # Simpler approach: use the submissions endpoint with accession
    # The accession number format is XXXXXXXXXX-YY-ZZZZZZ where X is CIK
    parts = accession_number.split("-")
    if len(parts) >= 1:
        potential_cik = parts[0].lstrip("0")
        if potential_cik.isdigit():
            return potential_cik

    return None
```

- [ ] **Step 4: Verify syntax**

Run: `python3 -m py_compile backend/app/services/edgar.py`
Expected: No output (success)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/edgar.py
git commit -m "feat(edgar): add EFTS search API for Form D filing discovery"
```

---

### Task 3: Add Discovery Filters to EDGAR Processor

**Files:**
- Modify: `backend/app/services/edgar_processor.py`

- [ ] **Step 1: Add SIC code whitelist constant**

Add after the `FundingRoundData` dataclass (after line 49):

```python
# SIC codes for venture-backed startups
SIC_WHITELIST: set[str] = set()
for _start, _end in [
    (2830, 2836),  # Pharmaceutical/Biotech
    (3570, 3579),  # Computer hardware
    (3600, 3699),  # Electronic components
    (3841, 3845),  # Medical devices/instruments
    (4812, 4813),  # Telecommunications
    (7371, 7379),  # Computer programming/software/services
    (8711, 8742),  # Engineering/R&D/Management consulting
]:
    SIC_WHITELIST.update(str(i) for i in range(_start, _end + 1))
SIC_WHITELIST.update(["3674", "3812", "4899", "5045"])

# Entity name patterns that indicate investment vehicles, not operating companies
ENTITY_EXCLUDE_PATTERNS = re.compile(
    r"\b(FUND|LP|PARTNERS|CAPITAL|TRUST|REIT|HOLDINGS)\b",
    re.IGNORECASE,
)

# Amount range for venture-backed startups
MIN_RAISE_AMOUNT = 500_000      # $500K
MAX_RAISE_AMOUNT = 500_000_000  # $500M
```

- [ ] **Step 2: Add `is_qualifying_filing` filter function**

```python
def is_qualifying_filing(form_d_data: FormDData, sic_code: str | None) -> bool:
    """Check if a Form D filing qualifies as a venture-backed startup."""
    # SIC code check
    if sic_code and sic_code not in SIC_WHITELIST:
        return False

    # Entity name exclusion
    if form_d_data.issuer_name and ENTITY_EXCLUDE_PATTERNS.search(form_d_data.issuer_name):
        return False

    # Amount range check
    amount = form_d_data.total_amount_sold
    if amount is None:
        return False
    if amount < MIN_RAISE_AMOUNT or amount > MAX_RAISE_AMOUNT:
        return False

    return True
```

- [ ] **Step 3: Add `infer_stage_from_amount` function**

```python
def infer_stage_from_amount(amount: float) -> str:
    """Infer startup stage from Form D raise amount."""
    if amount < 2_000_000:
        return "pre_seed"
    elif amount < 10_000_000:
        return "seed"
    elif amount < 50_000_000:
        return "series_a"
    elif amount < 150_000_000:
        return "series_b"
    else:
        return "series_c"
```

- [ ] **Step 4: Verify syntax**

Run: `python3 -m py_compile backend/app/services/edgar_processor.py`
Expected: No output (success)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/edgar_processor.py
git commit -m "feat(edgar): add SIC whitelist, entity filters, and stage inference for discovery"
```

---

### Task 4: Add Location Protection to Enrichment Pipeline

**Files:**
- Modify: `backend/app/services/enrichment.py`

The enrichment pipeline currently doesn't update `location_city`, `location_state`, or `location_country` (those fields aren't in the Perplexity prompt response). However, the spec requires explicit protection. We need to ensure the enrichment pipeline skips funding round replacement for EDGAR-sourced startups and preserves EDGAR data.

- [ ] **Step 1: Protect funding round data for EDGAR-sourced startups**

In `run_enrichment_pipeline()`, the pipeline currently **deletes all existing funding rounds** at line 632-636 and replaces them with Perplexity data. For EDGAR-discovered startups (those with `sec_cik` set), we must NOT replace EDGAR-sourced funding rounds. Instead, we should only add Perplexity rounds that don't already exist.

Find the funding rounds section (around line 632) and modify:

Replace:
```python
            # ----------------------------------------------------------
            # 4. Replace funding rounds
            # ----------------------------------------------------------
            await db.execute(
                delete(StartupFundingRound).where(
                    StartupFundingRound.startup_id == sid
                )
            )
            for idx, fr in enumerate(enriched.get("funding_rounds") or []):
                if not fr.get("round_name"):
                    continue
                db.add(
                    StartupFundingRound(
                        startup_id=sid,
                        round_name=fr["round_name"][:100],
                        amount=(fr.get("amount") or "")[:50] or None,
                        date=(fr.get("date") or "")[:20] or None,
                        lead_investor=(fr.get("lead_investor") or "")[:200] or None,
                        other_investors=(fr.get("other_investors") or "")[:1000] or None,
                        pre_money_valuation=(fr.get("pre_money_valuation") or "")[:50] or None,
                        post_money_valuation=(fr.get("post_money_valuation") or "")[:50] or None,
                        sort_order=idx,
                    )
                )
            await db.flush()
```

With:
```python
            # ----------------------------------------------------------
            # 4. Replace funding rounds (merge for EDGAR-sourced startups)
            # ----------------------------------------------------------
            if startup.sec_cik:
                # EDGAR-sourced startup: keep EDGAR rounds, supplement with Perplexity
                existing_rounds_result = await db.execute(
                    select(StartupFundingRound)
                    .where(StartupFundingRound.startup_id == sid)
                )
                existing_rounds = existing_rounds_result.scalars().all()
                existing_names = {r.round_name.lower() for r in existing_rounds if r.round_name}
                max_order = max((r.sort_order for r in existing_rounds), default=-1)
                for fr in enriched.get("funding_rounds") or []:
                    if not fr.get("round_name"):
                        continue
                    if fr["round_name"].lower() in existing_names:
                        # Update investor info on existing EDGAR round if missing
                        for er in existing_rounds:
                            if er.round_name and er.round_name.lower() == fr["round_name"].lower():
                                if not er.lead_investor and fr.get("lead_investor"):
                                    er.lead_investor = fr["lead_investor"][:200]
                                if not er.other_investors and fr.get("other_investors"):
                                    er.other_investors = fr["other_investors"][:1000]
                                if not er.round_name or er.round_name.startswith("Form D"):
                                    er.round_name = fr["round_name"][:100]
                                break
                        continue
                    max_order += 1
                    db.add(
                        StartupFundingRound(
                            startup_id=sid,
                            round_name=fr["round_name"][:100],
                            amount=(fr.get("amount") or "")[:50] or None,
                            date=(fr.get("date") or "")[:20] or None,
                            lead_investor=(fr.get("lead_investor") or "")[:200] or None,
                            other_investors=(fr.get("other_investors") or "")[:1000] or None,
                            pre_money_valuation=(fr.get("pre_money_valuation") or "")[:50] or None,
                            post_money_valuation=(fr.get("post_money_valuation") or "")[:50] or None,
                            sort_order=max_order,
                            data_source="perplexity",
                        )
                    )
            else:
                # Non-EDGAR startup: replace all rounds with Perplexity data
                await db.execute(
                    delete(StartupFundingRound).where(
                        StartupFundingRound.startup_id == sid
                    )
                )
                for idx, fr in enumerate(enriched.get("funding_rounds") or []):
                    if not fr.get("round_name"):
                        continue
                    db.add(
                        StartupFundingRound(
                            startup_id=sid,
                            round_name=fr["round_name"][:100],
                            amount=(fr.get("amount") or "")[:50] or None,
                            date=(fr.get("date") or "")[:20] or None,
                            lead_investor=(fr.get("lead_investor") or "")[:200] or None,
                            other_investors=(fr.get("other_investors") or "")[:1000] or None,
                            pre_money_valuation=(fr.get("pre_money_valuation") or "")[:50] or None,
                            post_money_valuation=(fr.get("post_money_valuation") or "")[:50] or None,
                            sort_order=idx,
                        )
                    )
            await db.flush()
```

- [ ] **Step 2: Protect location fields for EDGAR-sourced startups**

The enrichment pipeline's Perplexity prompt doesn't return location fields, but to be safe, add protection to the scalar field update section. After the `if enriched.get("business_model"):` block (around line 584), verify there's no location overwrite. The current code doesn't touch `location_city`, `location_state`, or `location_country` — this is already safe. No code change needed here, but verify by reading the file.

- [ ] **Step 3: Verify syntax**

Run: `python3 -m py_compile backend/app/services/enrichment.py`
Expected: No output (success)

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/enrichment.py
git commit -m "feat(edgar): protect EDGAR-sourced funding rounds and location during enrichment"
```

---

### Task 5: Add Discovery Step Executors to Worker

**Files:**
- Modify: `backend/app/services/edgar_worker.py`

This is the largest task. We add 4 new executor functions and update the worker configuration.

- [ ] **Step 1: Add imports**

Add these imports at the top of `edgar_worker.py`:

```python
from app.services.dedup import normalize_name, find_duplicate
from app.services.edgar_processor import (
    # existing imports stay
    form_d_to_funding_round,
    merge_funding_round,
    parse_form_d,
    parse_s1_html,
    parse_10k_html,
    resolve_cik,
    # new imports
    is_qualifying_filing,
    infer_stage_from_amount,
    SIC_WHITELIST,
)
from app.services.enrichment import run_enrichment_pipeline
from app.utils import slugify
```

- [ ] **Step 2: Add `_execute_discover_filings` function**

Add after `_execute_process_filing` (before `STEP_EXECUTORS`):

```python
async def _execute_discover_filings(
    db: AsyncSession, step: EdgarJobStep, job: EdgarJob
) -> None:
    """Execute discover_filings step: search EFTS for Form D filings, filter, generate extract steps."""
    discover_days = step.params.get("discover_days", 365)
    end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start_date = (datetime.now(timezone.utc) - __import__("datetime").timedelta(days=discover_days)).strftime("%Y-%m-%d")

    total_hits = 0
    qualifying = 0
    page_from = 0
    page_size = 100
    next_order = await _get_next_sort_order(db, job.id)

    while True:
        hits, total_count = await edgar.search_form_d_filings(
            start_date=start_date,
            end_date=end_date,
            page_from=page_from,
            page_size=page_size,
        )

        if not hits:
            break

        total_hits += len(hits)

        for hit in hits:
            # Generate an extract_company step for each hit
            extract_step = EdgarJobStep(
                job_id=job.id,
                step_type=EdgarStepType.extract_company,
                params={
                    "accession_number": hit.accession_number,
                    "entity_name": hit.entity_name,
                    "file_date": hit.file_date,
                    "cik": hit.cik,
                },
                sort_order=next_order,
            )
            db.add(extract_step)
            next_order += 1
            qualifying += 1

        page_from += page_size
        if page_from >= total_count:
            break

        # Flush periodically to avoid huge transaction
        if qualifying % 500 == 0:
            await db.flush()

    step.result = {
        "total_hits": total_hits,
        "extract_steps_created": qualifying,
        "date_range": f"{start_date} to {end_date}",
    }
    logger.info(f"Discovery: {total_hits} EFTS hits, {qualifying} extract steps created")
```

- [ ] **Step 3: Add `_execute_extract_company` function**

```python
async def _execute_extract_company(
    db: AsyncSession, step: EdgarJobStep, job: EdgarJob
) -> None:
    """Execute extract_company step: download Form D XML, parse, filter, dedup, generate add_startup step."""
    accession = step.params["accession_number"]
    entity_name = step.params.get("entity_name", "")
    cik = step.params.get("cik")

    if not cik:
        cik = await edgar.get_cik_from_accession(accession)
        if not cik:
            step.result = {"action": "skipped", "reason": "Could not resolve CIK"}
            return

    # Get company info (includes SIC code)
    company_info = await edgar.get_company_info(cik)
    sic_code = company_info.get("sic", "")

    # Check SIC code first (before downloading the full filing)
    if sic_code and sic_code not in SIC_WHITELIST:
        step.result = {"action": "skipped", "reason": f"SIC {sic_code} not in whitelist"}
        return

    # Get filings to find the primary document for this accession
    filings = await edgar.get_filings(cik)
    target_filing = None
    for f in filings:
        if f.accession_number == accession:
            target_filing = f
            break

    if not target_filing:
        # Try to construct the filing URL directly
        step.result = {"action": "skipped", "reason": "Filing not found in index"}
        return

    # Download and parse Form D
    try:
        doc_text = await edgar.download_filing(cik, accession, target_filing.primary_document)
        form_d_data = parse_form_d(doc_text)
    except Exception as e:
        step.result = {"action": "skipped", "reason": f"Parse failed: {str(e)[:200]}"}
        return

    # Apply qualifying filters
    if not is_qualifying_filing(form_d_data, sic_code):
        amount = form_d_data.total_amount_sold
        step.result = {
            "action": "skipped",
            "reason": "Did not pass qualifying filters",
            "amount": amount,
            "sic": sic_code,
            "entity_name": form_d_data.issuer_name or entity_name,
        }
        return

    issuer_name = form_d_data.issuer_name or entity_name
    amount = form_d_data.total_amount_sold or 0

    # Dedup check 1: CIK match
    existing_cik_result = await db.execute(
        select(Startup).where(Startup.sec_cik == cik)
    )
    existing_by_cik = existing_cik_result.scalar_one_or_none()
    if existing_by_cik:
        step.result = {
            "action": "duplicate",
            "reason": "CIK already in database",
            "existing_startup": existing_by_cik.name,
            "existing_id": str(existing_by_cik.id),
        }
        return

    # Dedup check 2: Name match
    dup = await find_duplicate(db, issuer_name)
    if dup:
        # Optionally update sec_cik on existing startup if missing
        existing_result = await db.execute(select(Startup).where(Startup.id == dup["id"]))
        existing = existing_result.scalar_one_or_none()
        if existing and not existing.sec_cik:
            existing.sec_cik = cik
        step.result = {
            "action": "duplicate",
            "reason": "Name match in database",
            "existing_startup": dup["name"],
            "existing_id": dup["id"],
            "cik_updated": bool(existing and not existing.sec_cik),
        }
        return

    # Qualifying new company — generate add_startup step
    state = company_info.get("state_of_incorporation", "") or company_info.get("state", "")
    next_order = await _get_next_sort_order(db, job.id)
    add_step = EdgarJobStep(
        job_id=job.id,
        step_type=EdgarStepType.add_startup,
        params={
            "issuer_name": issuer_name,
            "cik": cik,
            "sic_code": sic_code,
            "sic_description": company_info.get("sic_description", ""),
            "state": state,
            "amount": amount,
            "date_of_first_sale": form_d_data.date_of_first_sale,
            "number_of_investors": form_d_data.number_of_investors,
            "accession_number": accession,
            "filing_date": step.params.get("file_date", ""),
        },
        sort_order=next_order,
    )
    db.add(add_step)

    step.result = {
        "action": "new_company",
        "issuer_name": issuer_name,
        "cik": cik,
        "amount": amount,
        "sic": sic_code,
    }
    logger.info(f"Discovery: new company candidate — {issuer_name} (CIK {cik}, ${amount:,.0f})")
```

- [ ] **Step 4: Add `_execute_add_startup` function**

```python
async def _execute_add_startup(
    db: AsyncSession, step: EdgarJobStep, job: EdgarJob
) -> None:
    """Execute add_startup step: create Startup + FundingRound, generate enrich step."""
    from app.models.funding_round import StartupFundingRound
    from app.models.startup import StartupStage, StartupStatus

    issuer_name = step.params["issuer_name"]
    cik = step.params["cik"]
    state = step.params.get("state", "")
    amount = step.params.get("amount", 0)
    date_of_first_sale = step.params.get("date_of_first_sale")
    filing_date = step.params.get("filing_date", "")
    accession = step.params.get("accession_number", "")
    sic_description = step.params.get("sic_description", "")
    number_of_investors = step.params.get("number_of_investors")

    # Infer stage from amount
    stage_str = infer_stage_from_amount(amount)
    stage = StartupStage(stage_str)

    # Generate slug
    slug = slugify(issuer_name)
    # Ensure unique slug
    existing_slug = await db.execute(select(Startup).where(Startup.slug == slug))
    if existing_slug.scalar_one_or_none():
        slug = f"{slug}-{cik}"

    # Create startup
    startup = Startup(
        name=issuer_name,
        slug=slug,
        description=f"Discovered via SEC Form D filing. {sic_description}".strip(),
        stage=stage,
        status=StartupStatus.pending,
        location_state=state if state else None,
        location_country="US",
        sec_cik=cik,
    )
    db.add(startup)
    await db.flush()

    # Create initial funding round from EDGAR data
    from app.services.edgar_processor import _format_amount
    round_amount = _format_amount(amount) if amount else None
    round_date = date_of_first_sale or filing_date

    funding_round = StartupFundingRound(
        startup_id=startup.id,
        round_name=f"Form D ({round_date or 'undated'})",
        amount=round_amount,
        date=round_date,
        sort_order=0,
        data_source="edgar",
    )
    db.add(funding_round)

    # Generate enrich_startup step
    next_order = await _get_next_sort_order(db, job.id)
    enrich_step = EdgarJobStep(
        job_id=job.id,
        step_type=EdgarStepType.enrich_startup,
        params={
            "startup_id": str(startup.id),
            "startup_name": issuer_name,
        },
        sort_order=next_order,
    )
    db.add(enrich_step)

    step.result = {
        "action": "created",
        "startup_id": str(startup.id),
        "startup_name": issuer_name,
        "stage": stage_str,
        "amount": round_amount,
    }
    logger.info(f"Discovery: created startup {issuer_name} (stage={stage_str}, CIK={cik})")
```

- [ ] **Step 5: Add `_execute_enrich_startup` function**

```python
async def _execute_enrich_startup(
    db: AsyncSession, step: EdgarJobStep, job: EdgarJob
) -> None:
    """Execute enrich_startup step: run Perplexity enrichment pipeline."""
    startup_id = step.params["startup_id"]
    startup_name = step.params.get("startup_name", "")

    try:
        await run_enrichment_pipeline(startup_id)
        step.result = {
            "action": "enriched",
            "startup_name": startup_name,
        }
        logger.info(f"Discovery: enriched {startup_name}")
    except Exception as e:
        step.result = {
            "action": "enrichment_failed",
            "startup_name": startup_name,
            "error": str(e)[:200],
        }
        # Don't raise — enrichment failure is non-fatal, the startup was still created
        logger.warning(f"Discovery: enrichment failed for {startup_name}: {e}")
```

- [ ] **Step 6: Register executors and update worker preferences**

Update `STEP_EXECUTORS` dict:

```python
STEP_EXECUTORS = {
    EdgarStepType.resolve_cik: _execute_resolve_cik,
    EdgarStepType.fetch_filings: _execute_fetch_filings,
    EdgarStepType.process_filing: _execute_process_filing,
    EdgarStepType.discover_filings: _execute_discover_filings,
    EdgarStepType.extract_company: _execute_extract_company,
    EdgarStepType.add_startup: _execute_add_startup,
    EdgarStepType.enrich_startup: _execute_enrich_startup,
}
```

Update `STEP_DELAYS` to include new step types:

```python
STEP_DELAYS = {
    EdgarStepType.resolve_cik: 1.0,
    EdgarStepType.fetch_filings: 0.5,
    EdgarStepType.process_filing: 1.0,
    EdgarStepType.discover_filings: 0.2,
    EdgarStepType.extract_company: 1.0,
    EdgarStepType.add_startup: 0.5,
    EdgarStepType.enrich_startup: 2.0,
}
```

- [ ] **Step 7: Update `_update_progress` for discovery mode**

Add discovery-specific progress tracking. In `_update_progress`, add after the existing step counting loop (after line 87):

Add these counters inside the function:

```python
    # Discovery-mode counters
    filings_discovered = 0
    companies_extracted = 0
    duplicates_skipped = 0
    startups_created = 0
    enrichments_completed = 0
    enrichments_failed = 0

    for step in all_steps:
        # ... existing counting code stays ...

        # Discovery mode counting
        if step.step_type == EdgarStepType.discover_filings and step.status == EdgarStepStatus.completed:
            if step.result:
                filings_discovered += step.result.get("extract_steps_created", 0)
        elif step.step_type == EdgarStepType.extract_company and step.status == EdgarStepStatus.completed:
            companies_extracted += 1
            if step.result:
                if step.result.get("action") == "duplicate":
                    duplicates_skipped += 1
        elif step.step_type == EdgarStepType.add_startup and step.status == EdgarStepStatus.completed:
            if step.result and step.result.get("action") == "created":
                startups_created += 1
        elif step.step_type == EdgarStepType.enrich_startup and step.status == EdgarStepStatus.completed:
            if step.result:
                if step.result.get("action") == "enriched":
                    enrichments_completed += 1
                elif step.result.get("action") == "enrichment_failed":
                    enrichments_failed += 1
```

Add discovery counters to the summary dict:

```python
    # Add discovery-specific counters if this is a discover job
    total_extract = len([s for s in all_steps if s.step_type == EdgarStepType.extract_company])
    total_enrich = len([s for s in all_steps if s.step_type == EdgarStepType.enrich_startup])

    if total_extract > 0 or filings_discovered > 0:
        summary["filings_discovered"] = filings_discovered
        summary["companies_extracted"] = companies_extracted
        summary["extract_total"] = total_extract
        summary["duplicates_skipped"] = duplicates_skipped
        summary["startups_created"] = startups_created
        summary["enrichments_completed"] = enrichments_completed
        summary["enrichments_failed"] = enrichments_failed
        summary["enrich_total"] = total_enrich
```

Update the phase detection to include discovery phases:

```python
    has_pending_discover = any(
        s.step_type == EdgarStepType.discover_filings and s.status == EdgarStepStatus.pending
        for s in all_steps
    )
    has_pending_extract = any(
        s.step_type == EdgarStepType.extract_company and s.status == EdgarStepStatus.pending
        for s in all_steps
    )
    has_pending_add = any(
        s.step_type == EdgarStepType.add_startup and s.status == EdgarStepStatus.pending
        for s in all_steps
    )
    has_pending_enrich = any(
        s.step_type == EdgarStepType.enrich_startup and s.status == EdgarStepStatus.pending
        for s in all_steps
    )

    if has_pending_resolve:
        job.current_phase = EdgarJobPhase.resolving_ciks
    elif has_pending_fetch:
        job.current_phase = EdgarJobPhase.fetching_filings
    elif has_pending_process:
        job.current_phase = EdgarJobPhase.processing_filings
    elif has_pending_discover:
        job.current_phase = EdgarJobPhase.discovering
    elif has_pending_extract:
        job.current_phase = EdgarJobPhase.extracting
    elif has_pending_add:
        job.current_phase = EdgarJobPhase.adding
    elif has_pending_enrich:
        job.current_phase = EdgarJobPhase.enriching
    else:
        job.current_phase = EdgarJobPhase.complete
```

- [ ] **Step 8: Verify syntax**

Run: `python3 -m py_compile backend/app/services/edgar_worker.py`
Expected: No output (success)

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/edgar_worker.py
git commit -m "feat(edgar): add discovery step executors and progress tracking to worker"
```

---

### Task 6: Add Discovery Mode to Admin API

**Files:**
- Modify: `backend/app/api/admin_edgar.py`

- [ ] **Step 1: Add `discover_days` to `EdgarStartRequest`**

```python
class EdgarStartRequest(BaseModel):
    scan_mode: str = "full"
    discover_days: int = 365
```

- [ ] **Step 2: Add discover mode branch in `start_edgar_scan`**

After the existing job creation at line 50 (`await db.flush()`), add a branch for discover mode. Replace the block from line 52 to line 103 with:

```python
    sort_order = 0

    if body.scan_mode == "discover":
        # Discovery mode: generate a single discover_filings step
        job.current_phase = EdgarJobPhase.discovering
        step = EdgarJobStep(
            job_id=job.id,
            step_type=EdgarStepType.discover_filings,
            params={"discover_days": body.discover_days},
            sort_order=0,
        )
        db.add(step)
        sort_order = 1

        job.progress_summary = {
            "filings_discovered": 0,
            "companies_extracted": 0,
            "extract_total": 0,
            "duplicates_skipped": 0,
            "startups_created": 0,
            "enrichments_completed": 0,
            "enrichments_failed": 0,
            "enrich_total": 0,
        }
    else:
        # Existing scan mode logic (resolve_cik + fetch_filings)
        cik_query = (
            select(Startup.id, Startup.name)
            .where(Startup.location_country == "US")
            .where(Startup.sec_cik.is_(None))
        )
        if body.scan_mode == "new_only":
            cik_query = cik_query.where(Startup.edgar_last_scanned_at.is_(None))

        cik_result = await db.execute(cik_query)
        for startup_id, startup_name in cik_result.all():
            step = EdgarJobStep(
                job_id=job.id,
                step_type=EdgarStepType.resolve_cik,
                params={"startup_id": str(startup_id), "startup_name": startup_name},
                sort_order=sort_order,
            )
            db.add(step)
            sort_order += 1

        fetch_query = (
            select(Startup.id, Startup.name, Startup.sec_cik)
            .where(Startup.sec_cik.is_not(None))
        )
        fetch_result = await db.execute(fetch_query)
        for startup_id, startup_name, sec_cik in fetch_result.all():
            step = EdgarJobStep(
                job_id=job.id,
                step_type=EdgarStepType.fetch_filings,
                params={
                    "startup_id": str(startup_id),
                    "startup_name": startup_name,
                    "cik": sec_cik,
                },
                sort_order=sort_order,
            )
            db.add(step)
            sort_order += 1

        job.progress_summary = {
            "startups_total": sort_order,
            "startups_scanned": 0,
            "ciks_matched": 0,
            "filings_found": 0,
            "filings_total": 0,
            "filings_processed": 0,
            "rounds_updated": 0,
            "rounds_created": 0,
            "valuations_added": 0,
        }
```

- [ ] **Step 3: Add log formatting for discovery step types**

In the `get_edgar_log` endpoint, add formatting for the 4 new step types. After the `elif s.step_type == EdgarStepType.process_filing:` block (around line 348), add:

```python
        elif s.step_type == EdgarStepType.discover_filings:
            if s.status == EdgarStepStatus.completed:
                created = r.get("extract_steps_created", 0)
                date_range = r.get("date_range", "")
                msg = f"Discovered {created} Form D filings ({date_range})"
            elif s.status == EdgarStepStatus.running:
                msg = "Searching EDGAR for Form D filings..."
            else:
                msg = f"Discovery search failed: {s.error or 'unknown'}"

        elif s.step_type == EdgarStepType.extract_company:
            entity = p.get("entity_name", "") or r.get("issuer_name", "")
            if s.status == EdgarStepStatus.completed:
                action = r.get("action", "")
                if action == "new_company":
                    amount = r.get("amount", 0)
                    msg = f"New: {entity}"
                    if amount:
                        msg += f" (${amount:,.0f})" if isinstance(amount, (int, float)) else f" ({amount})"
                elif action == "duplicate":
                    existing = r.get("existing_startup", "")
                    msg = f"Duplicate: {entity} → {existing}"
                else:
                    reason = r.get("reason", "filtered")
                    msg = f"Skipped: {entity} ({reason})"
            elif s.status == EdgarStepStatus.running:
                msg = f"Extracting: {entity}..."
            else:
                msg = f"Extract failed for {entity}: {s.error or 'unknown'}"

        elif s.step_type == EdgarStepType.add_startup:
            name = p.get("issuer_name", "") or r.get("startup_name", "")
            if s.status == EdgarStepStatus.completed:
                stage = r.get("stage", "")
                amount = r.get("amount", "")
                msg = f"Created: {name} ({stage})"
                if amount:
                    msg += f" — {amount}"
            elif s.status == EdgarStepStatus.running:
                msg = f"Creating startup: {name}..."
            else:
                msg = f"Failed to create {name}: {s.error or 'unknown'}"

        elif s.step_type == EdgarStepType.enrich_startup:
            name = p.get("startup_name", "")
            if s.status == EdgarStepStatus.completed:
                action = r.get("action", "")
                if action == "enriched":
                    msg = f"Enriched: {name}"
                else:
                    msg = f"Enrichment failed: {name} — {r.get('error', '')}"
            elif s.status == EdgarStepStatus.running:
                msg = f"Enriching: {name}..."
            else:
                msg = f"Enrichment failed for {name}: {s.error or 'unknown'}"
```

- [ ] **Step 4: Verify syntax**

Run: `python3 -m py_compile backend/app/api/admin_edgar.py`
Expected: No output (success)

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/admin_edgar.py
git commit -m "feat(edgar): add discover mode to API with discover_days param and log formatting"
```

---

### Task 7: Update Admin Frontend API Client

**Files:**
- Modify: `admin/lib/api.ts`

- [ ] **Step 1: Update `startEdgar` to accept discover_days**

Replace the existing `startEdgar` method:

```typescript
  async startEdgar(token: string, scanMode: string, discoverDays?: number) {
    const body: Record<string, any> = { scan_mode: scanMode };
    if (discoverDays !== undefined) {
      body.discover_days = discoverDays;
    }
    return apiFetch<{ job_id: string; status: string; total_steps: number }>(
      "/api/admin/edgar/start",
      token,
      { method: "POST", body: JSON.stringify(body) }
    );
  },
```

- [ ] **Step 2: Verify build**

Run: `cd admin && npx next build --no-lint 2>&1 | tail -5`
Expected: Build succeeds (or at least no TS errors in api.ts)

- [ ] **Step 3: Commit**

```bash
git add admin/lib/api.ts
git commit -m "feat(edgar): update admin API client to support discover_days parameter"
```

---

### Task 8: Add Discovery UI to Admin EDGAR Page

**Files:**
- Modify: `admin/app/edgar/page.tsx`

- [ ] **Step 1: Add phase labels for discovery phases**

Update `PHASE_LABELS`:

```typescript
const PHASE_LABELS: Record<string, string> = {
  resolving_ciks: "Resolving CIKs",
  fetching_filings: "Fetching Filings",
  processing_filings: "Processing Filings",
  complete: "Complete",
  discovering: "Discovering Filings",
  extracting: "Extracting Companies",
  adding: "Creating Startups",
  enriching: "Enriching with Perplexity",
};
```

- [ ] **Step 2: Add `discoverDays` state variable**

Add after the `elapsed` state declaration (line 52):

```typescript
  const [discoverDays, setDiscoverDays] = useState(365);
```

- [ ] **Step 3: Add `handleDiscover` function**

Add after `handleCancel`:

```typescript
  async function handleDiscover() {
    if (!token) return;
    setLoading(true);
    try {
      await adminApi.startEdgar(token, "discover", discoverDays);
      await fetchData();
    } catch (e: any) {
      alert(e.message || "Failed to start discovery");
    }
    setLoading(false);
  }
```

- [ ] **Step 4: Add "Discover New" button and days input to control bar**

In the control bar JSX, after the "Scan New Only" button (inside the `{canStart && (` block), add:

```tsx
              <div className="w-px h-6 bg-border mx-1" />
              <button
                onClick={handleDiscover}
                disabled={loading}
                className="px-4 py-2 text-sm font-medium rounded bg-score-high text-white hover:opacity-90 disabled:opacity-50 transition"
              >
                Discover New
              </button>
              <div className="flex items-center gap-1.5">
                <input
                  type="number"
                  value={discoverDays}
                  onChange={(e) => setDiscoverDays(Math.max(1, parseInt(e.target.value) || 365))}
                  className="w-16 px-2 py-1.5 text-sm rounded border border-border bg-background text-text-primary text-center tabular-nums"
                  min={1}
                  max={3650}
                />
                <span className="text-xs text-text-tertiary">days</span>
              </div>
```

- [ ] **Step 5: Add discovery progress cards**

Determine which progress cards to show based on scan_mode. Replace the entire `grid grid-cols-3 md:grid-cols-6` div with:

```tsx
          <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
            {job.scan_mode === "discover" ? (
              <>
                <div>
                  <p className="text-xs text-text-tertiary">Filings Discovered</p>
                  <p className="text-sm font-medium text-text-primary tabular-nums">
                    {summary.filings_discovered || 0}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-text-tertiary">Companies Extracted</p>
                  <p className="text-sm font-medium text-text-primary tabular-nums">
                    {summary.companies_extracted || 0} / {summary.extract_total || 0}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-text-tertiary">Duplicates Skipped</p>
                  <p className="text-sm font-medium text-text-tertiary tabular-nums">
                    {summary.duplicates_skipped || 0}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-text-tertiary">Startups Created</p>
                  <p className="text-sm font-medium text-score-high tabular-nums">
                    {summary.startups_created || 0}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-text-tertiary">Enriched</p>
                  <p className="text-sm font-medium text-score-high tabular-nums">
                    {summary.enrichments_completed || 0} / {summary.enrich_total || 0}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-text-tertiary">Enrich Failed</p>
                  <p className="text-sm font-medium text-red-600 tabular-nums">
                    {summary.enrichments_failed || 0}
                  </p>
                </div>
              </>
            ) : (
              <>
                <div>
                  <p className="text-xs text-text-tertiary">Startups Scanned</p>
                  <p className="text-sm font-medium text-text-primary tabular-nums">
                    {summary.startups_scanned || 0} / {summary.startups_total || 0}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-text-tertiary">CIKs Matched</p>
                  <p className="text-sm font-medium text-text-primary tabular-nums">
                    {summary.ciks_matched || 0}
                    {summary.startups_scanned > 0 && (
                      <span className="text-text-tertiary text-xs ml-1">({matchRate}%)</span>
                    )}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-text-tertiary">Filings Found</p>
                  <p className="text-sm font-medium text-text-primary tabular-nums">{summary.filings_found || 0}</p>
                </div>
                <div>
                  <p className="text-xs text-text-tertiary">Filings Processed</p>
                  <p className="text-sm font-medium text-text-primary tabular-nums">
                    {summary.filings_processed || 0} / {summary.filings_total || 0}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-text-tertiary">Rounds Updated</p>
                  <p className="text-sm font-medium text-score-high tabular-nums">
                    {(summary.rounds_updated || 0) + (summary.rounds_created || 0)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-text-tertiary">Valuations Added</p>
                  <p className="text-sm font-medium text-score-high tabular-nums">{summary.valuations_added || 0}</p>
                </div>
              </>
            )}
          </div>
```

- [ ] **Step 6: Verify build**

Run: `cd admin && npx next build --no-lint 2>&1 | tail -5`
Expected: Build succeeds

- [ ] **Step 7: Commit**

```bash
git add admin/app/edgar/page.tsx
git commit -m "feat(edgar): add Discover New button, days input, and discovery progress cards to admin UI"
```

---

## Self-Review

**Spec coverage:**
- `discover_filings` step type — Task 1 (enum), Task 5 Step 2 (executor), Task 6 Step 2 (API creation)
- `extract_company` step type — Task 1 (enum), Task 5 Step 3 (executor)
- `add_startup` step type — Task 1 (enum), Task 5 Step 4 (executor)
- `enrich_startup` step type — Task 1 (enum), Task 5 Step 5 (executor)
- EFTS search API — Task 2
- SIC code whitelist — Task 3 Step 1
- Entity name exclusion — Task 3 Step 1
- Amount filter ($500K–$500M) — Task 3 Step 1-2
- Stage inference from amount — Task 3 Step 3
- Dedup (normalize_name + CIK) — Task 5 Step 3
- CIK backfill on duplicates — Task 5 Step 3
- Startup creation with EDGAR data — Task 5 Step 4
- Initial funding round with data_source="edgar" — Task 5 Step 4
- Enrichment pipeline integration — Task 5 Step 5
- Location protection (EDGAR location authoritative) — Task 4 (enrichment doesn't touch location fields, funding rounds protected)
- `discover_days` field on request — Task 6 Step 1
- Job creation branch for discover mode — Task 6 Step 2
- Log message formatting for new step types — Task 6 Step 3
- "Discover New" button — Task 8 Step 4
- Days input field — Task 8 Step 4
- Discovery progress cards — Task 8 Step 5

**Placeholder scan:** No TBD/TODO/placeholder patterns found.

**Type consistency:** All function names, param names, enum values, and result keys are consistent across tasks.
