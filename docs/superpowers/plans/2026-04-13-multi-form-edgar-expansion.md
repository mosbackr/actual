# Multi-Form EDGAR Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand EDGAR discovery from Form D-only to five SEC form types (D, S-1, 10-K, Form C, Form 1-A) with form-specific parsers, data priority merge, and field-level provenance tracking.

**Architecture:** One `discover_filings` step per form type (parallel-safe), form-aware `extract_company` with per-form parsing and filtering, data priority merge on startup fields (`S-1 > 10-K > Form C > Form 1-A > Form D > Perplexity`), and two new JSON columns (`form_sources`, `data_sources`) on the Startup model for provenance.

**Tech Stack:** Python/FastAPI, SQLAlchemy, Alembic, PostgreSQL JSONB, httpx, Claude API (Anthropic), Perplexity API, Next.js/React (admin + frontend)

---

## File Structure

### Backend — New files
- `backend/alembic/versions/xxxx_add_form_provenance_columns.py` — Migration for `form_sources` and `data_sources`

### Backend — Modified files
- `backend/app/models/startup.py` — Add `form_sources` and `data_sources` columns
- `backend/app/services/edgar.py` — Add EFTS search functions for S-1, 10-K, Form C, Form 1-A; add generic `EdgarEFTSHit` dataclass
- `backend/app/services/edgar_processor.py` — Add Form C XML parser, Form 1-A HTML parser, S-1 company data parser, 10-K company data parser, qualifying logic per form, data priority merge utility
- `backend/app/services/edgar_worker.py` — Form-aware `_execute_discover_filings`, `_execute_extract_company`, `_execute_add_startup` with provenance; update progress counters
- `backend/app/services/enrichment.py` — Update `run_enrichment_pipeline` to write `data_sources` for each field it sets
- `backend/app/api/admin_edgar.py` — Accept `form_types` param, generate one discover step per form type, per-form progress counters, update log messages

### Frontend — Modified files
- `admin/app/edgar/page.tsx` — Form type checkboxes in scan dialog, per-form progress display
- `frontend/app/startups/[slug]/page.tsx` — Data source labels/tooltips per field
- `frontend/app/startups/page.tsx` — Form source badges on startup cards
- `admin/app/startups/[id]/page.tsx` — Data source labels in admin detail view

---

## Task 1: Database Migration — Add Provenance Columns

**Files:**
- Create: `backend/alembic/versions/xxxx_add_form_provenance_columns.py`
- Modify: `backend/app/models/startup.py`

- [ ] **Step 1: Add columns to the Startup model**

In `backend/app/models/startup.py`, add two new columns after the `entity_type` column (line 109):

```python
from sqlalchemy.dialects.postgresql import JSON, TSVECTOR, UUID

# ... existing columns ...

    form_sources: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    data_sources: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
```

Also add `text` to the existing `sqlalchemy` import line:

```python
from sqlalchemy import Column, Date, DateTime, Enum, Float, ForeignKey, String, Table, Text, func, text
```

- [ ] **Step 2: Generate the Alembic migration**

Run: `cd /Users/leemosbacker/acutal/backend && alembic revision --autogenerate -m "add form_sources and data_sources to startups"`

- [ ] **Step 3: Verify the migration file**

Open the generated migration file and verify it contains:

```python
def upgrade() -> None:
    op.add_column("startups", sa.Column("form_sources", sa.JSON(), server_default=sa.text("'[]'::jsonb"), nullable=False))
    op.add_column("startups", sa.Column("data_sources", sa.JSON(), server_default=sa.text("'{}'::jsonb"), nullable=False))

def downgrade() -> None:
    op.drop_column("startups", "data_sources")
    op.drop_column("startups", "form_sources")
```

If autogenerate didn't produce this, write it manually.

- [ ] **Step 4: Run the migration locally (or on server)**

Run: `cd /Users/leemosbacker/acutal/backend && alembic upgrade head`

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/startup.py backend/alembic/versions/*form_provenance*
git commit -m "feat: add form_sources and data_sources provenance columns to startups"
```

---

## Task 2: EFTS Search Functions for All Form Types

**Files:**
- Modify: `backend/app/services/edgar.py`

- [ ] **Step 1: Add a generic EdgarEFTSHit dataclass**

Replace the existing `EdgarFormDHit` with a generic dataclass. Add after `EdgarFiling` (line 64):

```python
@dataclass
class EdgarEFTSHit:
    """A filing hit from EDGAR EFTS full-text search."""
    accession_number: str
    entity_name: str
    file_date: str
    file_num: str | None
    cik: str | None
    form_type: str  # "D", "S-1", "10-K", "C", "1-A" etc.
```

Keep `EdgarFormDHit` as an alias for backwards compatibility (the worker currently references it):

```python
# Backwards compat — existing code references EdgarFormDHit
EdgarFormDHit = EdgarEFTSHit
```

- [ ] **Step 2: Refactor search_form_d_filings into a generic _search_efts**

Add a private generic function and refactor `search_form_d_filings` to call it. Replace lines 204-260:

```python
async def _search_efts(
    forms: str,
    start_date: str,
    end_date: str,
    page_from: int = 0,
    page_size: int = 100,
) -> tuple[list[EdgarEFTSHit], int]:
    """Generic EFTS search. `forms` is the comma-separated forms= parameter."""
    url = (
        f"https://efts.sec.gov/LATEST/search-index"
        f"?forms={forms}&dateRange=custom"
        f"&startdt={start_date}&enddt={end_date}"
        f"&from={page_from}&size={page_size}"
    )

    try:
        resp = await _rate_limited_get(url)
    except httpx.HTTPStatusError as e:
        logger.warning(f"EDGAR EFTS search failed for forms={forms}: {e}")
        return [], 0

    data = resp.json()
    total = data.get("hits", {}).get("total", {}).get("value", 0)
    raw_hits = data.get("hits", {}).get("hits", [])

    hits = []
    for hit in raw_hits:
        source = hit.get("_source", {})
        raw_id = hit.get("_id", "")

        accession = raw_id.split(":")[0] if ":" in raw_id else raw_id

        display_names = source.get("display_names", [])
        entity_name = display_names[0] if display_names else ""
        if " (CIK " in entity_name:
            entity_name = entity_name.split(" (CIK ")[0].strip()
        file_date = source.get("file_date", "")
        file_num_list = source.get("file_num", [])
        file_num = file_num_list[0] if file_num_list else ""

        ciks = source.get("ciks", [])
        cik = ciks[0].lstrip("0") if ciks else None

        # Determine actual form type from source
        form_types = source.get("forms", [])
        form_type = form_types[0] if form_types else forms.split(",")[0]

        hits.append(EdgarEFTSHit(
            accession_number=accession,
            entity_name=entity_name,
            file_date=file_date,
            file_num=file_num,
            cik=cik,
            form_type=form_type,
        ))

    return hits, total


async def search_form_d_filings(
    start_date: str,
    end_date: str,
    page_from: int = 0,
    page_size: int = 100,
) -> tuple[list[EdgarEFTSHit], int]:
    """Search EDGAR EFTS for Form D filings within a date range."""
    return await _search_efts("D", start_date, end_date, page_from, page_size)


async def search_s1_filings(
    start_date: str,
    end_date: str,
    page_from: int = 0,
    page_size: int = 100,
) -> tuple[list[EdgarEFTSHit], int]:
    """Search EDGAR EFTS for S-1 filings within a date range."""
    return await _search_efts("S-1,S-1/A", start_date, end_date, page_from, page_size)


async def search_10k_filings(
    start_date: str,
    end_date: str,
    page_from: int = 0,
    page_size: int = 100,
) -> tuple[list[EdgarEFTSHit], int]:
    """Search EDGAR EFTS for 10-K filings within a date range."""
    return await _search_efts("10-K,10-K/A", start_date, end_date, page_from, page_size)


async def search_form_c_filings(
    start_date: str,
    end_date: str,
    page_from: int = 0,
    page_size: int = 100,
) -> tuple[list[EdgarEFTSHit], int]:
    """Search EDGAR EFTS for Form C filings within a date range."""
    return await _search_efts("C,C-U,C/A", start_date, end_date, page_from, page_size)


async def search_form_1a_filings(
    start_date: str,
    end_date: str,
    page_from: int = 0,
    page_size: int = 100,
) -> tuple[list[EdgarEFTSHit], int]:
    """Search EDGAR EFTS for Form 1-A filings within a date range."""
    return await _search_efts("1-A,1-A/A", start_date, end_date, page_from, page_size)
```

- [ ] **Step 3: Update get_filings to include Form C and 1-A**

In `get_filings()` (line 144), expand the target forms set:

```python
    target_forms = {"D", "D/A", "S-1", "S-1/A", "10-K", "10-K/A", "C", "C-U", "C/A", "1-A", "1-A/A"}
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/edgar.py
git commit -m "feat: add EFTS search functions for S-1, 10-K, Form C, Form 1-A"
```

---

## Task 3: Form C XML Parser

**Files:**
- Modify: `backend/app/services/edgar_processor.py`

- [ ] **Step 1: Add FormCData dataclass**

Add after `FormDData` (line 36):

```python
@dataclass
class FormCData:
    """Structured data extracted from a Form C filing (Regulation Crowdfunding)."""
    company_name: str | None = None
    cik: str | None = None
    state: str | None = None
    description: str | None = None
    business_plan: str | None = None
    employee_count: str | None = None
    revenue_most_recent: float | None = None
    net_income_most_recent: float | None = None
    target_amount: float | None = None
    maximum_amount: float | None = None
    use_of_proceeds: str | None = None
    officers: list[dict] = field(default_factory=list)  # [{"name": ..., "title": ...}]
    officer_compensation: str | None = None
```

- [ ] **Step 2: Implement parse_form_c function**

Add after `parse_form_d` (after line 176):

```python
def parse_form_c(xml_text: str) -> FormCData:
    """Parse Form C XML and extract crowdfunding offering data."""
    root = ET.fromstring(xml_text)

    # Remove namespace prefixes for easier access
    for elem in root.iter():
        if "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]
        for key in list(elem.attrib):
            if "}" in key:
                new_key = key.split("}", 1)[1]
                elem.attrib[new_key] = elem.attrib.pop(key)

    data = FormCData()

    # Company name
    for tag in ["issuerName", "nameOfIssuer", "companyName", "entityName"]:
        el = root.find(f".//{tag}")
        if el is not None and el.text:
            data.company_name = el.text.strip()
            break

    # State
    for tag in ["issuerStateOrCountry", "stateOfOrganization", "jurisdictionOrganization"]:
        el = root.find(f".//{tag}")
        if el is not None and el.text:
            data.state = el.text.strip()
            break

    # Description / business plan
    for tag in ["descriptionOfBusiness", "businessPlanDescription", "companyDescription"]:
        el = root.find(f".//{tag}")
        if el is not None and el.text:
            data.description = el.text.strip()
            break

    for tag in ["businessPlan", "materialBusinessPlan"]:
        el = root.find(f".//{tag}")
        if el is not None and el.text:
            data.business_plan = el.text.strip()
            break

    # Employee count
    for tag in ["numberOfEmployees", "employeeCount"]:
        el = root.find(f".//{tag}")
        if el is not None and el.text:
            data.employee_count = el.text.strip()
            break

    # Financial data
    for tag in ["totalRevenueMostRecentFiscalYear", "revenuesMostRecentFiscalYear", "totalAssetsMostRecentFiscalYear"]:
        el = root.find(f".//{tag}")
        if el is not None and el.text:
            try:
                data.revenue_most_recent = float(el.text.replace(",", "").replace("$", ""))
            except ValueError:
                pass
            break

    for tag in ["netIncomeMostRecentFiscalYear", "taxableIncomeMostRecentFiscalYear"]:
        el = root.find(f".//{tag}")
        if el is not None and el.text:
            try:
                data.net_income_most_recent = float(el.text.replace(",", "").replace("$", ""))
            except ValueError:
                pass
            break

    # Offering amounts
    for tag in ["targetOfferingAmount", "targetAmount"]:
        el = root.find(f".//{tag}")
        if el is not None and el.text:
            try:
                data.target_amount = float(el.text.replace(",", "").replace("$", ""))
            except ValueError:
                pass
            break

    for tag in ["maximumOfferingAmount", "overSubscriptionAmount", "maximumAmount"]:
        el = root.find(f".//{tag}")
        if el is not None and el.text:
            try:
                data.maximum_amount = float(el.text.replace(",", "").replace("$", ""))
            except ValueError:
                pass
            break

    # Use of proceeds
    for tag in ["useOfProceeds", "descriptionUseOfProceeds"]:
        el = root.find(f".//{tag}")
        if el is not None and el.text:
            data.use_of_proceeds = el.text.strip()
            break

    # Officers/directors
    for officer_el in root.findall(".//officer") + root.findall(".//director") + root.findall(".//officerDirector"):
        name_el = officer_el.find("officerName") or officer_el.find("name") or officer_el.find("nameOfPerson")
        title_el = officer_el.find("officerTitle") or officer_el.find("title") or officer_el.find("titleOfOfficer")
        if name_el is not None and name_el.text:
            data.officers.append({
                "name": name_el.text.strip(),
                "title": title_el.text.strip() if title_el is not None and title_el.text else None,
            })

    # Officer compensation
    for tag in ["compensationAmount", "totalCompensation"]:
        el = root.find(f".//{tag}")
        if el is not None and el.text:
            data.officer_compensation = el.text.strip()
            break

    return data
```

- [ ] **Step 3: Add qualifying filter for Form C**

Add after `is_qualifying_filing` (after line 93):

```python
# Form C amount range (Reg Crowdfunding caps at $5M)
FORM_C_MIN_AMOUNT = 50_000       # $50K
FORM_C_MAX_AMOUNT = 5_000_000    # $5M

# Form 1-A amount range (Reg A caps at $75M)
FORM_1A_MIN_AMOUNT = 500_000     # $500K
FORM_1A_MAX_AMOUNT = 75_000_000  # $75M


def is_qualifying_form_c(form_c_data: FormCData) -> bool:
    """Check if a Form C filing qualifies as a startup worth tracking."""
    amount = form_c_data.target_amount or form_c_data.maximum_amount
    if amount is None:
        return False
    if amount < FORM_C_MIN_AMOUNT or amount > FORM_C_MAX_AMOUNT:
        return False
    return True
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/edgar_processor.py
git commit -m "feat: add Form C XML parser and qualifying filter"
```

---

## Task 4: Form 1-A HTML Parser (Claude API)

**Files:**
- Modify: `backend/app/services/edgar_processor.py`

- [ ] **Step 1: Add Form1AData dataclass**

Add after `FormCData`:

```python
@dataclass
class Form1AData:
    """Structured data extracted from a Form 1-A filing (Regulation A)."""
    company_name: str | None = None
    description: str | None = None
    use_of_proceeds: str | None = None
    offering_amount: float | None = None
    business_model: str | None = None
    officers: list[dict] = field(default_factory=list)
    risk_factors: str | None = None
    revenue: str | None = None
    net_income: str | None = None
    employee_count: str | None = None
```

- [ ] **Step 2: Implement parse_form_1a_html function**

Add after `parse_10k_html`:

```python
async def parse_form_1a_html(html_text: str, company_name: str) -> Form1AData:
    """Parse Form 1-A (Reg A) HTML using Claude to extract offering data."""
    sections_to_find = [
        r"business",
        r"use of proceeds",
        r"management",
        r"compensation",
        r"risk factors",
        r"financial statements",
        r"capitalization",
        r"dilution",
    ]

    extracted = _extract_html_sections(html_text, sections_to_find, max_chars=50000)
    if not extracted:
        extracted = html_text[:30000]

    system = """You are a financial document parser. Extract company data from SEC Form 1-A (Regulation A) offering circulars.

Return a JSON object with:
- company_name: string or null
- description: business description (2-3 paragraphs, string or null)
- use_of_proceeds: how the company will use the money raised (string or null)
- offering_amount: total offering amount as a number (float or null, e.g. 20000000 for $20M)
- business_model: brief description of business model (string or null)
- officers: array of {name, title} for management team
- risk_factors: key risks summary (string or null)
- revenue: latest annual revenue as string e.g. "$1.2M" (string or null)
- net_income: latest net income as string (string or null)
- employee_count: as string e.g. "25" (string or null)

Return ONLY the JSON object, no other text."""

    user = f"Company: {company_name}\n\nExtracted Form 1-A sections:\n\n{extracted}"

    try:
        response = await _call_claude(system, user)
        import json
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group(0))
            data = Form1AData(
                company_name=parsed.get("company_name"),
                description=parsed.get("description"),
                use_of_proceeds=parsed.get("use_of_proceeds"),
                business_model=parsed.get("business_model"),
                risk_factors=parsed.get("risk_factors"),
                revenue=parsed.get("revenue"),
                net_income=parsed.get("net_income"),
                employee_count=parsed.get("employee_count"),
            )
            if parsed.get("offering_amount"):
                try:
                    data.offering_amount = float(parsed["offering_amount"])
                except (ValueError, TypeError):
                    pass
            for o in parsed.get("officers") or []:
                if o.get("name"):
                    data.officers.append({"name": o["name"], "title": o.get("title")})
            return data
    except Exception as e:
        logger.error(f"Claude Form 1-A parsing failed for {company_name}: {e}")

    return Form1AData()


def is_qualifying_form_1a(form_1a_data: Form1AData) -> bool:
    """Check if a Form 1-A filing qualifies."""
    amount = form_1a_data.offering_amount
    if amount is None:
        return False
    if amount < FORM_1A_MIN_AMOUNT or amount > FORM_1A_MAX_AMOUNT:
        return False
    return True
```

- [ ] **Step 3: Add S-1 company data parser for discovery**

The existing `parse_s1_html` only returns funding rounds. For discovery, we need company data too. Add:

```python
async def parse_s1_company_data(html_text: str, company_name: str) -> dict:
    """Parse S-1 filing HTML using Claude to extract company data for discovery.

    Returns a dict with: description, revenue, business_model, founders, total_funding, etc.
    """
    sections_to_find = [
        r"business",
        r"use of proceeds",
        r"management",
        r"selected financial data",
        r"risk factors",
    ]

    extracted = _extract_html_sections(html_text, sections_to_find, max_chars=50000)
    if not extracted:
        extracted = html_text[:30000]

    system = """You are a financial document parser. Extract company data from an SEC S-1 registration statement.

Return a JSON object with:
- description: business description (2-3 paragraphs, string or null)
- revenue: latest annual revenue as string e.g. "$50M" (string or null)
- employee_count: as string e.g. "500" (string or null)
- total_funding: total funding raised as string e.g. "$120M" (string or null)
- business_model: brief business model description (string or null)
- founders: array of {name, title} for founders/key executives
- funding_rounds: array of {round_name, amount, date, lead_investor, other_investors, pre_money_valuation, post_money_valuation}

Return ONLY the JSON object, no other text."""

    user = f"Company: {company_name}\n\nExtracted S-1 sections:\n\n{extracted}"

    try:
        response = await _call_claude(system, user)
        import json
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
    except Exception as e:
        logger.error(f"Claude S-1 company data parsing failed for {company_name}: {e}")

    return {}
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/edgar_processor.py
git commit -m "feat: add Form 1-A HTML parser, S-1 company data parser, and qualifying filters"
```

---

## Task 5: Data Priority Merge Logic

**Files:**
- Modify: `backend/app/services/edgar_processor.py`

- [ ] **Step 1: Add source priority constants and merge function**

Add at the top of the file (after the imports section, around line 12):

```python
# Data source priority — higher number wins
SOURCE_PRIORITY = {
    "S-1": 60,
    "S-1/A": 60,
    "10-K": 50,
    "10-K/A": 50,
    "C": 40,
    "C-U": 40,
    "C/A": 40,
    "1-A": 30,
    "1-A/A": 30,
    "D": 20,
    "D/A": 20,
    "perplexity": 10,
    "logo.dev": 10,
}


def should_overwrite(field_name: str, new_source: str, current_sources: dict) -> bool:
    """Check if new_source has higher priority than the current source for a field.

    Returns True if the field should be overwritten.
    """
    current_source = current_sources.get(field_name)
    if current_source is None:
        return True  # No existing source — always set
    new_priority = SOURCE_PRIORITY.get(new_source, 0)
    current_priority = SOURCE_PRIORITY.get(current_source, 0)
    return new_priority > current_priority


def merge_field(
    startup,
    field_name: str,
    new_value,
    source: str,
    data_sources: dict,
) -> dict:
    """Set a field on startup if the value is non-empty and the source has priority.

    Returns updated data_sources dict.
    """
    if new_value is None or new_value == "" or new_value == 0:
        return data_sources
    if not should_overwrite(field_name, source, data_sources):
        return data_sources
    setattr(startup, field_name, new_value)
    data_sources[field_name] = source
    return data_sources
```

- [ ] **Step 2: Add helper to normalize form type to source key**

```python
def normalize_form_source(form_type: str) -> str:
    """Normalize a filing form type to its source key for provenance.

    Maps variants like 'S-1/A' -> 'S-1', 'C-U' -> 'C', 'D/A' -> 'D', etc.
    """
    mapping = {
        "D": "D", "D/A": "D",
        "S-1": "S-1", "S-1/A": "S-1",
        "10-K": "10-K", "10-K/A": "10-K",
        "C": "C", "C-U": "C", "C/A": "C",
        "1-A": "1-A", "1-A/A": "1-A",
    }
    return mapping.get(form_type, form_type)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/edgar_processor.py
git commit -m "feat: add data source priority merge logic for multi-form provenance"
```

---

## Task 6: Form-Aware Discovery Worker

**Files:**
- Modify: `backend/app/services/edgar_worker.py`

- [ ] **Step 1: Add per-form EFTS search dispatcher**

Add a mapping dict near the top of the file (after `STEP_DELAYS`):

```python
from app.services.edgar import (
    search_form_d_filings,
    search_s1_filings,
    search_10k_filings,
    search_form_c_filings,
    search_form_1a_filings,
)

# Maps form_type key to EFTS search function
FORM_SEARCH_FUNCTIONS = {
    "D": search_form_d_filings,
    "S-1": search_s1_filings,
    "10-K": search_10k_filings,
    "C": search_form_c_filings,
    "1-A": search_form_1a_filings,
}

# Human-readable form labels for logging
FORM_LABELS = {
    "D": "Form D",
    "S-1": "S-1",
    "10-K": "10-K",
    "C": "Form C",
    "1-A": "Form 1-A",
}
```

- [ ] **Step 2: Update _execute_discover_filings to be form-aware**

Replace the entire `_execute_discover_filings` function (lines 375-432):

```python
async def _execute_discover_filings(
    db: AsyncSession, step: EdgarJobStep, job: EdgarJob
) -> None:
    """Execute discover_filings step: search EFTS for filings by form type, generate extract steps."""
    from datetime import timedelta

    discover_days = step.params.get("discover_days", 365)
    form_type = step.params.get("form_type", "D")
    end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start_date = (datetime.now(timezone.utc) - timedelta(days=discover_days)).strftime("%Y-%m-%d")

    search_fn = FORM_SEARCH_FUNCTIONS.get(form_type, search_form_d_filings)
    label = FORM_LABELS.get(form_type, form_type)

    total_hits = 0
    qualifying = 0
    page_from = 0
    page_size = 100
    next_order = await _get_next_sort_order(db, job.id)

    while True:
        hits, total_count = await search_fn(
            start_date=start_date,
            end_date=end_date,
            page_from=page_from,
            page_size=page_size,
        )

        if not hits:
            break

        total_hits += len(hits)

        for hit in hits:
            extract_step = EdgarJobStep(
                job_id=job.id,
                step_type=EdgarStepType.extract_company,
                params={
                    "accession_number": hit.accession_number,
                    "entity_name": hit.entity_name,
                    "file_date": hit.file_date,
                    "cik": hit.cik,
                    "form_type": form_type,
                },
                sort_order=next_order,
            )
            db.add(extract_step)
            next_order += 1
            qualifying += 1

        page_from += page_size
        if page_from >= total_count:
            break

        if qualifying % 500 == 0:
            await db.flush()

    step.result = {
        "total_hits": total_hits,
        "extract_steps_created": qualifying,
        "date_range": f"{start_date} to {end_date}",
        "form_type": form_type,
    }
    logger.info(f"Discovery ({label}): {total_hits} EFTS hits, {qualifying} extract steps created")
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/edgar_worker.py
git commit -m "feat: form-aware discover_filings step with per-type EFTS search"
```

---

## Task 7: Form-Aware Extract Company

**Files:**
- Modify: `backend/app/services/edgar_worker.py`

This is the most complex task. Each form type has different parsing, qualifying, and data extraction logic.

- [ ] **Step 1: Add form-specific imports**

Update the imports from `edgar_processor` at the top of `edgar_worker.py`:

```python
from app.services.edgar_processor import (
    FormCData,
    Form1AData,
    form_d_to_funding_round,
    is_qualifying_filing,
    is_qualifying_form_c,
    is_qualifying_form_1a,
    infer_stage_from_amount,
    merge_funding_round,
    normalize_form_source,
    parse_form_c,
    parse_form_d,
    parse_form_1a_html,
    parse_s1_company_data,
    parse_s1_html,
    parse_10k_html,
    resolve_cik,
    SIC_WHITELIST,
    ENTITY_EXCLUDE_PATTERNS,
)
```

- [ ] **Step 2: Replace _execute_extract_company with form-aware version**

Replace the entire function (lines 435-551). The new version dispatches to form-specific handlers:

```python
async def _execute_extract_company(
    db: AsyncSession, step: EdgarJobStep, job: EdgarJob
) -> None:
    """Execute extract_company step: parse filing per form type, filter, dedup, generate add_startup step."""
    accession = step.params["accession_number"]
    entity_name = step.params.get("entity_name", "")
    cik = step.params.get("cik")
    form_type = step.params.get("form_type", "D")

    if not cik:
        cik = await edgar.get_cik_from_accession(accession)
        if not cik:
            step.result = {"action": "skipped", "reason": "Could not resolve CIK"}
            return

    company_info = await edgar.get_company_info(cik)
    sic_code = company_info.get("sic", "")

    # --- Form-specific parsing and qualifying ---
    if form_type == "D":
        result = await _extract_form_d(db, step, job, accession, entity_name, cik, company_info, sic_code)
    elif form_type in ("S-1",):
        result = await _extract_s1(db, step, job, accession, entity_name, cik, company_info, sic_code)
    elif form_type in ("10-K",):
        result = await _extract_10k(db, step, job, accession, entity_name, cik, company_info, sic_code)
    elif form_type in ("C",):
        result = await _extract_form_c(db, step, job, accession, entity_name, cik, company_info, sic_code)
    elif form_type in ("1-A",):
        result = await _extract_form_1a(db, step, job, accession, entity_name, cik, company_info, sic_code)
    else:
        step.result = {"action": "skipped", "reason": f"Unknown form type: {form_type}"}
        return

    # result is None if the sub-handler already set step.result (skip/dup)
    # result is a dict of add_startup params if we should proceed


async def _dedup_check(db: AsyncSession, step: EdgarJobStep, cik: str, issuer_name: str) -> bool:
    """Run dedup checks. Returns True if duplicate found (step.result is set). False if new."""
    # CIK match
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
        return True

    # Name match
    dup = await find_duplicate(db, issuer_name)
    if dup:
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
        return True

    return False


async def _create_add_step(
    db: AsyncSession, step: EdgarJobStep, job: EdgarJob,
    issuer_name: str, cik: str, company_info: dict, sic_code: str,
    form_type: str, amount: float, extra_params: dict | None = None,
) -> None:
    """Create an add_startup step for a qualifying new company."""
    state = company_info.get("state_of_incorporation", "") or company_info.get("state", "")
    next_order = await _get_next_sort_order(db, job.id)

    params = {
        "issuer_name": issuer_name,
        "cik": cik,
        "sic_code": sic_code,
        "sic_description": company_info.get("sic_description", ""),
        "state": state,
        "amount": amount,
        "form_type": form_type,
        "accession_number": step.params.get("accession_number", ""),
        "filing_date": step.params.get("file_date", ""),
    }
    if extra_params:
        params.update(extra_params)

    add_step = EdgarJobStep(
        job_id=job.id,
        step_type=EdgarStepType.add_startup,
        params=params,
        sort_order=next_order,
    )
    db.add(add_step)

    step.result = {
        "action": "new_company",
        "issuer_name": issuer_name,
        "cik": cik,
        "amount": amount,
        "sic": sic_code,
        "form_type": form_type,
    }
    label = FORM_LABELS.get(form_type, form_type)
    logger.info(f"Discovery ({label}): new company candidate — {issuer_name} (CIK {cik}, ${amount:,.0f})")


async def _extract_form_d(db, step, job, accession, entity_name, cik, company_info, sic_code):
    """Form D extraction — existing logic."""
    if sic_code and sic_code not in SIC_WHITELIST:
        step.result = {"action": "skipped", "reason": f"SIC {sic_code} not in whitelist", "form_type": "D"}
        return

    filings = await edgar.get_filings(cik)
    target_filing = next((f for f in filings if f.accession_number == accession), None)
    if not target_filing:
        step.result = {"action": "skipped", "reason": "Filing not found in index", "form_type": "D"}
        return

    try:
        doc_name = target_filing.primary_document
        if doc_name.startswith("xsl"):
            doc_name = doc_name.split("/", 1)[-1] if "/" in doc_name else doc_name
        doc_text = await edgar.download_filing(cik, accession, doc_name)
        form_d_data = parse_form_d(doc_text)
    except Exception as e:
        step.result = {"action": "skipped", "reason": f"Parse failed: {str(e)[:200]}", "form_type": "D"}
        return

    if not is_qualifying_filing(form_d_data, sic_code):
        step.result = {
            "action": "skipped", "reason": "Did not pass qualifying filters",
            "amount": form_d_data.total_amount_sold, "sic": sic_code,
            "entity_name": form_d_data.issuer_name or entity_name, "form_type": "D",
        }
        return

    issuer_name = form_d_data.issuer_name or entity_name
    amount = form_d_data.total_amount_sold or 0

    if await _dedup_check(db, step, cik, issuer_name):
        return

    await _create_add_step(
        db, step, job, issuer_name, cik, company_info, sic_code,
        form_type="D", amount=amount,
        extra_params={
            "date_of_first_sale": form_d_data.date_of_first_sale,
            "number_of_investors": form_d_data.number_of_investors,
        },
    )


async def _extract_s1(db, step, job, accession, entity_name, cik, company_info, sic_code):
    """S-1 extraction — every hit is a real company, skip SIC filter."""
    issuer_name = entity_name or company_info.get("name", "Unknown")

    if await _dedup_check(db, step, cik, issuer_name):
        return

    # Download and parse for company data
    filings = await edgar.get_filings(cik)
    target_filing = next((f for f in filings if f.accession_number == accession), None)

    parsed_data = {}
    if target_filing:
        try:
            doc_name = target_filing.primary_document
            if doc_name.startswith("xsl"):
                doc_name = doc_name.split("/", 1)[-1] if "/" in doc_name else doc_name
            doc_text = await edgar.download_filing(cik, accession, doc_name)
            parsed_data = await parse_s1_company_data(doc_text, issuer_name)
        except Exception as e:
            logger.warning(f"S-1 parse failed for {issuer_name}: {e}")

    await _create_add_step(
        db, step, job, issuer_name, cik, company_info, sic_code,
        form_type="S-1", amount=0,
        extra_params={"parsed_data": parsed_data},
    )


async def _extract_10k(db, step, job, accession, entity_name, cik, company_info, sic_code):
    """10-K extraction — apply SIC whitelist to filter old-economy companies."""
    if sic_code and sic_code not in SIC_WHITELIST:
        step.result = {"action": "skipped", "reason": f"SIC {sic_code} not in whitelist", "form_type": "10-K"}
        return

    issuer_name = entity_name or company_info.get("name", "Unknown")

    if await _dedup_check(db, step, cik, issuer_name):
        return

    # Download and parse for financial data
    filings = await edgar.get_filings(cik)
    target_filing = next((f for f in filings if f.accession_number == accession), None)

    parsed_data = {}
    if target_filing:
        try:
            doc_name = target_filing.primary_document
            if doc_name.startswith("xsl"):
                doc_name = doc_name.split("/", 1)[-1] if "/" in doc_name else doc_name
            doc_text = await edgar.download_filing(cik, accession, doc_name)
            parsed_data = await parse_10k_html(doc_text, issuer_name)
        except Exception as e:
            logger.warning(f"10-K parse failed for {issuer_name}: {e}")

    await _create_add_step(
        db, step, job, issuer_name, cik, company_info, sic_code,
        form_type="10-K", amount=0,
        extra_params={"parsed_data": parsed_data},
    )


async def _extract_form_c(db, step, job, accession, entity_name, cik, company_info, sic_code):
    """Form C extraction — parse XML, apply Form C amount threshold."""
    filings = await edgar.get_filings(cik)
    target_filing = next((f for f in filings if f.accession_number == accession), None)
    if not target_filing:
        step.result = {"action": "skipped", "reason": "Filing not found in index", "form_type": "C"}
        return

    try:
        doc_name = target_filing.primary_document
        if doc_name.startswith("xsl"):
            doc_name = doc_name.split("/", 1)[-1] if "/" in doc_name else doc_name
        doc_text = await edgar.download_filing(cik, accession, doc_name)
        form_c_data = parse_form_c(doc_text)
    except Exception as e:
        step.result = {"action": "skipped", "reason": f"Parse failed: {str(e)[:200]}", "form_type": "C"}
        return

    if not is_qualifying_form_c(form_c_data):
        step.result = {
            "action": "skipped", "reason": "Did not pass Form C qualifying filters",
            "amount": form_c_data.target_amount, "form_type": "C",
        }
        return

    issuer_name = form_c_data.company_name or entity_name
    amount = form_c_data.target_amount or form_c_data.maximum_amount or 0

    if await _dedup_check(db, step, cik, issuer_name):
        return

    await _create_add_step(
        db, step, job, issuer_name, cik, company_info, sic_code,
        form_type="C", amount=amount,
        extra_params={
            "parsed_data": {
                "description": form_c_data.description,
                "business_plan": form_c_data.business_plan,
                "employee_count": form_c_data.employee_count,
                "revenue": form_c_data.revenue_most_recent,
                "officers": form_c_data.officers,
            },
        },
    )


async def _extract_form_1a(db, step, job, accession, entity_name, cik, company_info, sic_code):
    """Form 1-A extraction — parse HTML via Claude, apply amount threshold."""
    filings = await edgar.get_filings(cik)
    target_filing = next((f for f in filings if f.accession_number == accession), None)
    if not target_filing:
        step.result = {"action": "skipped", "reason": "Filing not found in index", "form_type": "1-A"}
        return

    try:
        doc_name = target_filing.primary_document
        if doc_name.startswith("xsl"):
            doc_name = doc_name.split("/", 1)[-1] if "/" in doc_name else doc_name
        doc_text = await edgar.download_filing(cik, accession, doc_name)
        form_1a_data = await parse_form_1a_html(doc_text, entity_name)
    except Exception as e:
        step.result = {"action": "skipped", "reason": f"Parse failed: {str(e)[:200]}", "form_type": "1-A"}
        return

    if not is_qualifying_form_1a(form_1a_data):
        step.result = {
            "action": "skipped", "reason": "Did not pass Form 1-A qualifying filters",
            "amount": form_1a_data.offering_amount, "form_type": "1-A",
        }
        return

    issuer_name = form_1a_data.company_name or entity_name
    amount = form_1a_data.offering_amount or 0

    if await _dedup_check(db, step, cik, issuer_name):
        return

    await _create_add_step(
        db, step, job, issuer_name, cik, company_info, sic_code,
        form_type="1-A", amount=amount,
        extra_params={
            "parsed_data": {
                "description": form_1a_data.description,
                "business_model": form_1a_data.business_model,
                "employee_count": form_1a_data.employee_count,
                "revenue": form_1a_data.revenue,
                "officers": form_1a_data.officers,
            },
        },
    )
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/edgar_worker.py
git commit -m "feat: form-aware extract_company with per-type parsing, filtering, and dedup"
```

---

## Task 8: Form-Aware Add Startup with Provenance

**Files:**
- Modify: `backend/app/services/edgar_worker.py`

- [ ] **Step 1: Replace _execute_add_startup with provenance-aware version**

Replace the entire `_execute_add_startup` function (lines 554-638):

```python
async def _execute_add_startup(
    db: AsyncSession, step: EdgarJobStep, job: EdgarJob
) -> None:
    """Execute add_startup step: create Startup + FundingRound, set provenance, generate enrich step."""
    from app.models.funding_round import StartupFundingRound
    from app.models.startup import StartupStage, StartupStatus
    from app.services.edgar_processor import _format_amount, merge_field, normalize_form_source

    from app.models.startup import EntityType

    issuer_name = step.params["issuer_name"]
    cik = step.params["cik"]
    state = step.params.get("state", "")
    amount = step.params.get("amount", 0)
    form_type = step.params.get("form_type", "D")
    date_of_first_sale = step.params.get("date_of_first_sale")
    filing_date = step.params.get("filing_date", "")
    accession = step.params.get("accession_number", "")
    sic_description = step.params.get("sic_description", "")
    parsed_data = step.params.get("parsed_data", {})

    source_key = normalize_form_source(form_type)

    # Classification: skip for S-1 and Form C (virtually all startups), skip for 10-K (public companies)
    if form_type in ("S-1",):
        is_startup = True
    elif form_type in ("10-K",):
        is_startup = True  # Public companies are real companies
    elif form_type in ("C",):
        is_startup = True  # Reg Crowdfunding = virtually all startups
    else:
        # Form D and Form 1-A: run Perplexity classification
        is_startup = await _is_real_startup(issuer_name)

    stage_str = infer_stage_from_amount(amount) if amount else "seed"
    if form_type in ("10-K",):
        stage_str = "public"  # 10-K filers are public companies
    stage = StartupStage(stage_str)

    import uuid as _uuid
    slug = f"{slugify(issuer_name)}-{cik}"
    existing_slug = await db.execute(select(Startup).where(Startup.slug == slug))
    if existing_slug.scalar_one_or_none():
        slug = f"{slugify(issuer_name)}-{str(_uuid.uuid4())[:8]}"

    entity_type = EntityType.startup if is_startup else EntityType.fund
    form_label = FORM_LABELS.get(form_type, form_type)

    # Build initial data_sources from filing data
    data_sources = {}
    description_text = f"Discovered via SEC {form_label} filing. {sic_description}".strip()

    # Apply parsed data from filing if available
    startup_kwargs = {
        "name": issuer_name,
        "slug": slug,
        "description": description_text,
        "stage": stage,
        "status": StartupStatus.pending,
        "location_state": state if state else None,
        "location_country": "US",
        "sec_cik": cik,
        "entity_type": entity_type,
        "enrichment_status": "complete" if not is_startup else "none",
        "form_sources": [source_key],
        "data_sources": {},
    }

    startup = Startup(**startup_kwargs)
    db.add(startup)
    await db.flush()

    # Set provenance for base fields
    data_sources["location_state"] = source_key if state else None
    data_sources["location_country"] = source_key
    data_sources["stage"] = source_key

    # Apply parsed filing data with provenance
    if parsed_data:
        if parsed_data.get("description"):
            startup.description = parsed_data["description"]
            data_sources["description"] = source_key
        if parsed_data.get("business_model"):
            startup.business_model = str(parsed_data["business_model"])[:200]
            data_sources["business_model"] = source_key
        if parsed_data.get("employee_count"):
            startup.employee_count = str(parsed_data["employee_count"])[:50]
            data_sources["employee_count"] = source_key
        if parsed_data.get("revenue"):
            val = parsed_data["revenue"]
            startup.revenue_estimate = str(val)[:200] if not isinstance(val, (int, float)) else _format_amount(val)
            data_sources["revenue_estimate"] = source_key
        if parsed_data.get("total_funding"):
            startup.total_funding = str(parsed_data["total_funding"])[:100]
            data_sources["total_funding"] = source_key

        # Founders from filing
        if parsed_data.get("officers"):
            from app.models.founder import StartupFounder
            for idx, officer in enumerate(parsed_data["officers"]):
                if officer.get("name"):
                    db.add(StartupFounder(
                        startup_id=startup.id,
                        name=officer["name"][:200],
                        title=(officer.get("title") or "")[:200] or None,
                        is_founder=True,
                        sort_order=idx,
                    ))
            data_sources["founders"] = source_key

        # Funding rounds from S-1 parsed data
        if parsed_data.get("funding_rounds"):
            from app.models.funding_round import StartupFundingRound as FR
            for idx, fr in enumerate(parsed_data["funding_rounds"]):
                if fr.get("round_name") or fr.get("amount"):
                    db.add(FR(
                        startup_id=startup.id,
                        round_name=(fr.get("round_name") or f"{form_label} ({filing_date or 'undated'})")[:100],
                        amount=(fr.get("amount") or "")[:50] or None,
                        date=(fr.get("date") or "")[:20] or None,
                        lead_investor=(fr.get("lead_investor") or "")[:200] or None,
                        other_investors=(fr.get("other_investors") or "")[:1000] or None,
                        pre_money_valuation=(fr.get("pre_money_valuation") or "")[:50] or None,
                        post_money_valuation=(fr.get("post_money_valuation") or "")[:50] or None,
                        sort_order=idx,
                        data_source="edgar",
                    ))
            data_sources["funding_rounds"] = source_key

    # If no funding rounds from parsed data, create one from the Form D/C amount
    if not parsed_data.get("funding_rounds") and amount:
        round_amount = _format_amount(amount)
        round_date = date_of_first_sale or filing_date

        funding_round = StartupFundingRound(
            startup_id=startup.id,
            round_name=f"{form_label} ({round_date or 'undated'})",
            amount=round_amount,
            date=round_date,
            sort_order=0,
            data_source="edgar",
        )
        db.add(funding_round)
        data_sources["total_funding"] = source_key

    # Clean up None values from data_sources
    data_sources = {k: v for k, v in data_sources.items() if v is not None}
    startup.data_sources = data_sources

    # Only enrich actual startups — skip funds to save Perplexity credits
    if is_startup:
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

    round_amount = _format_amount(amount) if amount else None
    step.result = {
        "action": "created",
        "startup_id": str(startup.id),
        "startup_name": issuer_name,
        "entity_type": entity_type.value,
        "stage": stage_str,
        "amount": round_amount,
        "form_type": form_type,
    }
    logger.info(f"Discovery: created {entity_type.value} {issuer_name} (stage={stage_str}, form={form_type}, CIK={cik})")
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/edgar_worker.py
git commit -m "feat: form-aware add_startup with provenance tracking and parsed data population"
```

---

## Task 9: Enrichment Provenance Tracking

**Files:**
- Modify: `backend/app/services/enrichment.py`

- [ ] **Step 1: Update run_enrichment_pipeline to track data_sources**

In `run_enrichment_pipeline`, after loading the startup (line 536), load existing `data_sources`:

Find the section starting at line 554 (`# Update scalar fields on startup`) and replace the field-setting logic through line 593:

```python
            # Track which fields Perplexity fills
            data_sources = dict(startup.data_sources or {})

            # Update scalar fields — only if no higher-priority source already set them
            from app.services.edgar_processor import should_overwrite

            if enriched.get("website_url") and not startup.website_url:
                startup.website_url = enriched["website_url"][:500]
                data_sources["website_url"] = "perplexity"
            if enriched.get("tagline"):
                if should_overwrite("tagline", "perplexity", data_sources):
                    startup.tagline = enriched["tagline"][:500]
                    data_sources["tagline"] = "perplexity"
            if enriched.get("description"):
                if should_overwrite("description", "perplexity", data_sources):
                    startup.description = enriched["description"]
                    data_sources["description"] = "perplexity"
            if enriched.get("founded_date"):
                parsed_date = _parse_founded_date(enriched["founded_date"])
                if parsed_date and should_overwrite("founded_date", "perplexity", data_sources):
                    startup.founded_date = parsed_date
                    data_sources["founded_date"] = "perplexity"
            if enriched.get("total_funding"):
                if should_overwrite("total_funding", "perplexity", data_sources):
                    startup.total_funding = enriched["total_funding"][:100]
                    data_sources["total_funding"] = "perplexity"
            if enriched.get("employee_count"):
                if should_overwrite("employee_count", "perplexity", data_sources):
                    startup.employee_count = enriched["employee_count"][:50]
                    data_sources["employee_count"] = "perplexity"
            if enriched.get("linkedin_url"):
                if should_overwrite("linkedin_url", "perplexity", data_sources):
                    startup.linkedin_url = enriched["linkedin_url"][:500]
                    data_sources["linkedin_url"] = "perplexity"
            if enriched.get("twitter_url"):
                if should_overwrite("twitter_url", "perplexity", data_sources):
                    startup.twitter_url = enriched["twitter_url"][:500]
                    data_sources["twitter_url"] = "perplexity"
            if enriched.get("crunchbase_url"):
                if should_overwrite("crunchbase_url", "perplexity", data_sources):
                    startup.crunchbase_url = enriched["crunchbase_url"][:500]
                    data_sources["crunchbase_url"] = "perplexity"
            if enriched.get("competitors"):
                if should_overwrite("competitors", "perplexity", data_sources):
                    startup.competitors = enriched["competitors"]
                    data_sources["competitors"] = "perplexity"
            if enriched.get("tech_stack"):
                if should_overwrite("tech_stack", "perplexity", data_sources):
                    startup.tech_stack = enriched["tech_stack"]
                    data_sources["tech_stack"] = "perplexity"
            if enriched.get("key_metrics"):
                if should_overwrite("key_metrics", "perplexity", data_sources):
                    startup.key_metrics = enriched["key_metrics"]
                    data_sources["key_metrics"] = "perplexity"
            if enriched.get("hiring_signals"):
                if should_overwrite("hiring_signals", "perplexity", data_sources):
                    startup.hiring_signals = enriched["hiring_signals"]
                    data_sources["hiring_signals"] = "perplexity"
            if enriched.get("patents"):
                if should_overwrite("patents", "perplexity", data_sources):
                    startup.patents = enriched["patents"]
                    data_sources["patents"] = "perplexity"
            if enriched.get("company_status"):
                try:
                    if should_overwrite("company_status", "perplexity", data_sources):
                        startup.company_status = CompanyStatus(enriched["company_status"].lower().strip())
                        data_sources["company_status"] = "perplexity"
                except ValueError:
                    pass
            if enriched.get("revenue_estimate"):
                if should_overwrite("revenue_estimate", "perplexity", data_sources):
                    startup.revenue_estimate = enriched["revenue_estimate"][:200]
                    data_sources["revenue_estimate"] = "perplexity"
            if enriched.get("business_model"):
                if should_overwrite("business_model", "perplexity", data_sources):
                    startup.business_model = enriched["business_model"][:200]
                    data_sources["business_model"] = "perplexity"
```

- [ ] **Step 2: Track media and scoring provenance**

After the media section (around line 751), add:

```python
            if enriched.get("media"):
                data_sources["media"] = "perplexity"
```

After the `_fetch_logo_if_needed` call (around line 783), add:

```python
            if startup.logo_url and "logo.dev" in (startup.logo_url or ""):
                data_sources["logo_url"] = "logo.dev"
```

After the scoring section writes ai_score (around line 876), add:

```python
            data_sources["ai_score"] = "perplexity"
            if enriched.get("industries"):
                data_sources["industry"] = "perplexity"
```

- [ ] **Step 3: Save data_sources before final commit**

Just before `startup.enrichment_status = EnrichmentStatus.complete` (around line 890), add:

```python
            startup.data_sources = data_sources
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/enrichment.py
git commit -m "feat: enrichment pipeline tracks data_sources provenance per field"
```

---

## Task 10: Admin API — Form Types Parameter and Per-Form Progress

**Files:**
- Modify: `backend/app/api/admin_edgar.py`

- [ ] **Step 1: Update EdgarStartRequest to accept form_types**

Replace the `EdgarStartRequest` class (line 25):

```python
class EdgarStartRequest(BaseModel):
    scan_mode: str = "full"
    discover_days: int = 365
    form_types: list[str] = ["D", "S-1", "10-K", "C", "1-A"]
```

- [ ] **Step 2: Update start_edgar_scan to create one discover step per form type**

Replace the discover mode block (lines 55-76):

```python
    if body.scan_mode == "discover":
        job.current_phase = EdgarJobPhase.discovering

        for form_type in body.form_types:
            step = EdgarJobStep(
                job_id=job.id,
                step_type=EdgarStepType.discover_filings,
                params={"discover_days": body.discover_days, "form_type": form_type},
                sort_order=sort_order,
            )
            db.add(step)
            sort_order += 1

        job.progress_summary = {
            "filings_discovered": 0,
            "companies_extracted": 0,
            "extract_total": 0,
            "duplicates_skipped": 0,
            "startups_created": 0,
            "enrichments_completed": 0,
            "enrichments_failed": 0,
            "enrich_total": 0,
            "form_types": body.form_types,
        }
```

- [ ] **Step 3: Update log message formatting for form-aware discover_filings**

Replace the `discover_filings` log block (lines 374-382):

```python
        elif s.step_type == EdgarStepType.discover_filings:
            form_type = p.get("form_type", "D")
            form_labels = {"D": "Form D", "S-1": "S-1", "10-K": "10-K", "C": "Form C", "1-A": "Form 1-A"}
            label = form_labels.get(form_type, form_type)
            if s.status == EdgarStepStatus.completed:
                created = r.get("extract_steps_created", 0)
                date_range = r.get("date_range", "")
                msg = f"Discovered {created} {label} filings ({date_range})"
            elif s.status == EdgarStepStatus.running:
                msg = f"Searching EDGAR for {label} filings..."
            else:
                msg = f"Discovery search failed for {label}: {s.error or 'unknown'}"
```

- [ ] **Step 4: Update extract_company log to show form type**

In the `extract_company` log block (lines 384-402), add form type to messages:

```python
        elif s.step_type == EdgarStepType.extract_company:
            entity = p.get("entity_name", "") or r.get("issuer_name", "")
            form_type = p.get("form_type", "D")
            form_labels = {"D": "Form D", "S-1": "S-1", "10-K": "10-K", "C": "Form C", "1-A": "Form 1-A"}
            label = form_labels.get(form_type, form_type)
            if s.status == EdgarStepStatus.completed:
                action = r.get("action", "")
                if action == "new_company":
                    amount = r.get("amount", 0)
                    msg = f"New ({label}): {entity}"
                    if amount:
                        msg += f" (${amount:,.0f})" if isinstance(amount, (int, float)) else f" ({amount})"
                elif action == "duplicate":
                    existing = r.get("existing_startup", "")
                    msg = f"Duplicate ({label}): {entity} → {existing}"
                else:
                    reason = r.get("reason", "filtered")
                    msg = f"Skipped ({label}): {entity} ({reason})"
            elif s.status == EdgarStepStatus.running:
                msg = f"Extracting ({label}): {entity}..."
            else:
                msg = f"Extract failed ({label}) for {entity}: {s.error or 'unknown'}"
```

- [ ] **Step 5: Update add_startup log to show form type**

In the `add_startup` log block (lines 404-419):

```python
        elif s.step_type == EdgarStepType.add_startup:
            name = p.get("issuer_name", "") or r.get("startup_name", "")
            form_type = p.get("form_type", r.get("form_type", "D"))
            form_labels = {"D": "Form D", "S-1": "S-1", "10-K": "10-K", "C": "Form C", "1-A": "Form 1-A"}
            label = form_labels.get(form_type, form_type)
            if s.status == EdgarStepStatus.completed:
                entity_type = r.get("entity_type", "startup")
                stage = r.get("stage", "")
                amount = r.get("amount", "")
                if entity_type == "fund":
                    msg = f"Fund ({label}): {name} (saved, skipping enrichment)"
                else:
                    msg = f"Created ({label}): {name} ({stage})"
                if amount:
                    msg += f" — {amount}"
            elif s.status == EdgarStepStatus.running:
                msg = f"Classifying ({label}): {name}..."
            else:
                msg = f"Failed to create ({label}) {name}: {s.error or 'unknown'}"
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/admin_edgar.py
git commit -m "feat: admin API accepts form_types param, creates per-form discover steps, form-aware log messages"
```

---

## Task 11: Admin Frontend — Form Type Checkboxes and Per-Form Progress

**Files:**
- Modify: `admin/app/edgar/page.tsx`

- [ ] **Step 1: Add form type state and checkboxes**

Near the top of the component (after the existing state variables like `discoverDays`), add:

```tsx
const [formTypes, setFormTypes] = useState<string[]>(["D", "S-1", "10-K", "C", "1-A"]);

const FORM_OPTIONS = [
  { value: "D", label: "Form D" },
  { value: "S-1", label: "S-1" },
  { value: "10-K", label: "10-K" },
  { value: "C", label: "Form C" },
  { value: "1-A", label: "Form 1-A" },
];

const toggleFormType = (ft: string) => {
  setFormTypes(prev =>
    prev.includes(ft) ? prev.filter(t => t !== ft) : [...prev, ft]
  );
};

const toggleAll = () => {
  if (formTypes.length === FORM_OPTIONS.length) {
    setFormTypes([]);
  } else {
    setFormTypes(FORM_OPTIONS.map(o => o.value));
  }
};
```

- [ ] **Step 2: Add checkbox UI below the discover days input**

In the discover section of the JSX, after the days input field, add:

```tsx
<div className="mt-3">
  <div className="flex items-center justify-between mb-2">
    <span className="text-sm text-zinc-400">Form Types</span>
    <button
      onClick={toggleAll}
      className="text-xs text-blue-400 hover:text-blue-300"
    >
      {formTypes.length === FORM_OPTIONS.length ? "None" : "All"}
    </button>
  </div>
  <div className="flex flex-wrap gap-2">
    {FORM_OPTIONS.map(opt => (
      <label key={opt.value} className="flex items-center gap-1.5 cursor-pointer">
        <input
          type="checkbox"
          checked={formTypes.includes(opt.value)}
          onChange={() => toggleFormType(opt.value)}
          className="rounded border-zinc-600 bg-zinc-800 text-blue-500 focus:ring-blue-500/20"
        />
        <span className="text-sm text-zinc-300">{opt.label}</span>
      </label>
    ))}
  </div>
</div>
```

- [ ] **Step 3: Pass form_types in the discover API call**

Update the fetch call for "Discover New" to include `form_types`:

```tsx
body: JSON.stringify({
  scan_mode: "discover",
  discover_days: discoverDays,
  form_types: formTypes,
}),
```

- [ ] **Step 4: Add per-form progress display**

In the progress metrics section (discover mode), after the existing metric cards, add a per-form breakdown if `form_types` is present in the progress summary:

```tsx
{job.progress_summary?.form_types && (
  <div className="mt-4 pt-4 border-t border-zinc-700/50">
    <h4 className="text-sm font-medium text-zinc-400 mb-2">Discovery by Form Type</h4>
    <div className="space-y-1">
      {/* Show discover step results per form type from the log data */}
    </div>
  </div>
)}
```

Since the per-form counters come from individual discover step results, display them by reading the log entries. A simpler approach: show the form types being scanned as badges:

```tsx
{job.progress_summary?.form_types && (
  <div className="flex gap-1.5 mt-2">
    {job.progress_summary.form_types.map((ft: string) => (
      <span key={ft} className="px-2 py-0.5 text-xs rounded bg-zinc-700 text-zinc-300">
        {ft}
      </span>
    ))}
  </div>
)}
```

- [ ] **Step 5: Commit**

```bash
git add admin/app/edgar/page.tsx
git commit -m "feat: admin EDGAR page form type checkboxes and per-form progress display"
```

---

## Task 12: Startup API — Expose Provenance Data

**Files:**
- Modify: `backend/app/api/startups.py`

- [ ] **Step 1: Add form_sources and data_sources to startup detail response**

In the `get_startup` endpoint return dict (line 232), add two fields after `"slug"`:

```python
        "form_sources": startup.form_sources or [],
        "data_sources": startup.data_sources or {},
```

- [ ] **Step 2: Add form_sources to startup list response**

In the `list_startups` endpoint items list (line 105), add after `"tagline"`:

```python
                "form_sources": s.form_sources or [],
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/startups.py
git commit -m "feat: expose form_sources and data_sources in startup API responses"
```

---

## Task 13: Frontend — Data Source Display on Startup Detail Page

**Files:**
- Modify: `frontend/app/startups/[slug]/page.tsx`

- [ ] **Step 1: Add a SourceBadge component**

At the top of the file (or in a shared components file), add:

```tsx
function SourceBadge({ source }: { source: string | undefined }) {
  if (!source) return null;
  const labels: Record<string, string> = {
    "D": "Form D",
    "S-1": "S-1 Filing",
    "10-K": "10-K Filing",
    "C": "Form C",
    "1-A": "Form 1-A",
    "perplexity": "AI Research",
    "logo.dev": "Logo.dev",
  };
  const colors: Record<string, string> = {
    "D": "bg-amber-500/10 text-amber-400",
    "S-1": "bg-blue-500/10 text-blue-400",
    "10-K": "bg-green-500/10 text-green-400",
    "C": "bg-purple-500/10 text-purple-400",
    "1-A": "bg-cyan-500/10 text-cyan-400",
    "perplexity": "bg-zinc-500/10 text-zinc-400",
    "logo.dev": "bg-zinc-500/10 text-zinc-400",
  };
  return (
    <span
      className={`inline-flex items-center px-1.5 py-0.5 text-[10px] font-medium rounded ${colors[source] || "bg-zinc-500/10 text-zinc-400"}`}
      title={labels[source] || source}
    >
      {labels[source] || source}
    </span>
  );
}
```

- [ ] **Step 2: Add form source badges to the hero section**

After the company name / before the description, add:

```tsx
{startup.form_sources?.length > 0 && (
  <div className="flex gap-1 mt-1">
    {startup.form_sources.map((fs: string) => (
      <SourceBadge key={fs} source={fs} />
    ))}
  </div>
)}
```

- [ ] **Step 3: Add source labels next to key data fields**

Next to fields like description, revenue, employee count, etc., show the source:

```tsx
{/* Example: next to revenue_estimate */}
<div className="flex items-center gap-2">
  <span>{startup.revenue_estimate}</span>
  <SourceBadge source={startup.data_sources?.revenue_estimate} />
</div>
```

Apply this pattern to: `description`, `revenue_estimate`, `employee_count`, `total_funding`, `business_model`, `competitors`, `tech_stack`, `key_metrics`, `website_url`, `founded_date`.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/startups/\[slug\]/page.tsx
git commit -m "feat: show data source badges on startup detail page"
```

---

## Task 14: Frontend — Form Source Badges on Startup List Cards

**Files:**
- Modify: `frontend/app/startups/page.tsx`

- [ ] **Step 1: Add form source badges to startup cards**

In the startup card rendering, after the existing bottom row (stage badge, industry, score), add:

```tsx
{s.form_sources?.length > 0 && (
  <div className="flex gap-1 mt-1.5">
    {s.form_sources.map((fs: string) => (
      <span
        key={fs}
        className="px-1.5 py-0.5 text-[10px] font-medium rounded bg-zinc-700/50 text-zinc-400"
        title={`Data from ${fs}`}
      >
        {fs}
      </span>
    ))}
  </div>
)}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/startups/page.tsx
git commit -m "feat: show form source badges on startup list cards"
```

---

## Task 15: Admin Startup Detail — Data Source Labels

**Files:**
- Modify: `admin/app/startups/[id]/page.tsx`

- [ ] **Step 1: Add SourceBadge component to admin detail page**

Same `SourceBadge` component as Task 13 Step 1 (copy or extract to shared).

- [ ] **Step 2: Add form_sources display to the header area**

After the enrichment badge, add:

```tsx
{startup.form_sources?.length > 0 && (
  <div className="flex gap-1 mt-2">
    <span className="text-xs text-zinc-500 mr-1">SEC Forms:</span>
    {startup.form_sources.map((fs: string) => (
      <SourceBadge key={fs} source={fs} />
    ))}
  </div>
)}
```

- [ ] **Step 3: Add source indicators on data fields in Company Intel section**

In the Company Intel section, next to each field value, add `SourceBadge` reading from `startup.data_sources`:

```tsx
<SourceBadge source={startup.data_sources?.employee_count} />
```

- [ ] **Step 4: Commit**

```bash
git add admin/app/startups/\[id\]/page.tsx
git commit -m "feat: show data source labels on admin startup detail page"
```

---

## Task 16: Update Worker Progress Counters for Multi-Form

**Files:**
- Modify: `backend/app/services/edgar_worker.py`

- [ ] **Step 1: Update _update_progress to track per-form stats**

In `_update_progress`, add per-form tracking. After the existing counter variables (around line 86), add:

```python
    # Per-form counters
    per_form_discovered = {}  # form_type -> count
    per_form_created = {}
```

In the loop, where `discover_filings` is counted (around line 106), add:

```python
        elif step.step_type == EdgarStepType.discover_filings and step.status == EdgarStepStatus.completed:
            if step.result:
                count = step.result.get("extract_steps_created", 0)
                filings_discovered += count
                ft = step.params.get("form_type", "D")
                per_form_discovered[ft] = per_form_discovered.get(ft, 0) + count
```

Where `add_startup` is counted (around line 113), add:

```python
        elif step.step_type == EdgarStepType.add_startup and step.status == EdgarStepStatus.completed:
            if step.result and step.result.get("action") == "created":
                ft = step.params.get("form_type", step.result.get("form_type", "D"))
                if step.result.get("entity_type") == "fund":
                    duplicates_skipped += 1
                else:
                    startups_created += 1
                    per_form_created[ft] = per_form_created.get(ft, 0) + 1
```

Add the per-form data to the summary:

```python
    if per_form_discovered:
        summary["per_form_discovered"] = per_form_discovered
    if per_form_created:
        summary["per_form_created"] = per_form_created
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/edgar_worker.py
git commit -m "feat: track per-form discovery and creation counters in progress summary"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] EFTS search functions for all 5 form types (Task 2)
- [x] Form C XML parser (Task 3)
- [x] Form 1-A HTML/Claude parser (Task 4)
- [x] S-1 company data parser for discovery (Task 4)
- [x] Data priority merge logic (Task 5)
- [x] form_sources and data_sources columns (Task 1)
- [x] Form-aware discover_filings (Task 6)
- [x] Form-aware extract_company per form type (Task 7)
- [x] Form-aware add_startup with provenance (Task 8)
- [x] Enrichment provenance tracking (Task 9)
- [x] Admin API form_types param (Task 10)
- [x] Admin UI checkboxes (Task 11)
- [x] Per-form progress counters (Task 16)
- [x] Frontend data source display (Tasks 12-15)
- [x] Classification rules: skip for S-1/10-K/Form C, run for D/1-A (Task 8)
- [x] 10-K filers set to "public" stage (Task 8)
- [x] Log messages show form type (Task 10)

**Type consistency:** `EdgarEFTSHit` used consistently across search functions; `form_type` param threaded through discover → extract → add steps; `data_sources` and `form_sources` used consistently in model, worker, enrichment, and API responses.

**No placeholders:** All steps contain actual code. No TBDs or "implement later" markers.
