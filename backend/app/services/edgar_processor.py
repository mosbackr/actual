"""EDGAR Processor — parses filings and matches companies.

Form D: Direct XML parsing (no LLM needed).
S-1/10-K: Claude API extraction (unstructured HTML).
Company matching: CIK lookup + Claude verification.
"""
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.funding_round import StartupFundingRound
from app.models.startup import Startup
from app.services import edgar

logger = logging.getLogger(__name__)


@dataclass
class FormDData:
    """Structured data extracted from a Form D filing."""
    total_amount_sold: float | None = None
    total_amount_remaining: float | None = None
    number_of_investors: int | None = None
    min_investment_accepted: float | None = None
    date_of_first_sale: str | None = None
    federal_exemptions: list[str] = field(default_factory=list)
    issuer_name: str | None = None


@dataclass
class FundingRoundData:
    """Normalized funding round data from any filing type."""
    round_name: str | None = None
    amount: str | None = None
    date: str | None = None
    pre_money_valuation: str | None = None
    post_money_valuation: str | None = None
    lead_investor: str | None = None
    other_investors: str | None = None
    filing_type: str | None = None
    accession_number: str | None = None


def parse_form_d(xml_text: str) -> FormDData:
    """Parse Form D XML and extract funding data."""
    root = ET.fromstring(xml_text)

    # Remove namespace prefixes for easier access
    for elem in root.iter():
        if "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]
        for key in list(elem.attrib):
            if "}" in key:
                new_key = key.split("}", 1)[1]
                elem.attrib[new_key] = elem.attrib.pop(key)

    data = FormDData()

    # Issuer name
    issuer = root.find(".//issuerName") or root.find(".//entityName") or root.find(".//nameOfIssuer")
    if issuer is not None and issuer.text:
        data.issuer_name = issuer.text.strip()

    # Total amount sold
    for tag in ["totalAmountSold", "aggregateNetAssetValue"]:
        el = root.find(f".//{tag}")
        if el is not None and el.text:
            try:
                data.total_amount_sold = float(el.text.replace(",", "").replace("$", ""))
            except ValueError:
                pass
            break

    # Total amount remaining
    el = root.find(".//totalRemaining")
    if el is not None and el.text:
        try:
            data.total_amount_remaining = float(el.text.replace(",", "").replace("$", ""))
        except ValueError:
            pass

    # Number of investors
    el = root.find(".//totalNumberAlreadyInvested")
    if el is not None and el.text:
        try:
            data.number_of_investors = int(el.text)
        except ValueError:
            pass

    # Minimum investment accepted
    el = root.find(".//minimumInvestmentAccepted")
    if el is not None and el.text:
        try:
            data.min_investment_accepted = float(el.text.replace(",", "").replace("$", ""))
        except ValueError:
            pass

    # Date of first sale
    el = root.find(".//dateOfFirstSale")
    if el is not None:
        value_el = el.find("value") or el
        if value_el.text:
            data.date_of_first_sale = value_el.text.strip()

    # Federal exemptions
    for el in root.findall(".//federalExemptionsExclusions"):
        if el.text:
            data.federal_exemptions.append(el.text.strip())

    return data


def _format_amount(value: float) -> str:
    """Format a dollar amount as a human-readable string."""
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f}B"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"${value / 1_000:.0f}K"
    return f"${value:.0f}"


def form_d_to_funding_round(data: FormDData, filing: edgar.EdgarFiling) -> FundingRoundData:
    """Convert Form D data into a normalized FundingRoundData."""
    amount = None
    if data.total_amount_sold is not None and data.total_amount_sold > 0:
        amount = _format_amount(data.total_amount_sold)

    return FundingRoundData(
        round_name=None,
        amount=amount,
        date=data.date_of_first_sale or filing.filing_date,
        filing_type=filing.filing_type,
        accession_number=filing.accession_number,
    )


async def _call_claude(system_prompt: str, user_prompt: str) -> str:
    """Call Claude API and return the text response."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 4096,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"]


async def parse_s1_html(html_text: str, company_name: str) -> list[FundingRoundData]:
    """Parse S-1 filing HTML using Claude to extract funding history."""
    sections_to_find = [
        r"use of proceeds",
        r"capitalization",
        r"dilution",
        r"principal stockholders",
        r"description of capital stock",
        r"selected financial data",
    ]

    extracted = _extract_html_sections(html_text, sections_to_find, max_chars=50000)
    if not extracted:
        extracted = html_text[:30000]

    system = """You are a financial document parser. Extract funding round data from SEC S-1 filings.

Return a JSON array of funding rounds. Each round should have:
- round_name: e.g. "Series A", "Series B", "IPO" (string or null)
- amount: dollar amount as string e.g. "$50M", "$120M" (string or null)
- date: YYYY-MM-DD format (string or null)
- pre_money_valuation: dollar amount as string e.g. "$200M" (string or null)
- post_money_valuation: dollar amount as string e.g. "$250M" (string or null)
- lead_investor: name of lead investor (string or null)
- other_investors: comma-separated investor names (string or null)

Return ONLY the JSON array, no other text. If no funding rounds found, return [].
Mark estimated valuations with ~ prefix (e.g. "~$200M")."""

    user = f"Company: {company_name}\n\nExtracted S-1 sections:\n\n{extracted}"

    try:
        response = await _call_claude(system, user)
        import json
        json_match = re.search(r"\[.*\]", response, re.DOTALL)
        if json_match:
            rounds_raw = json.loads(json_match.group(0))
            return [
                FundingRoundData(
                    round_name=r.get("round_name"),
                    amount=r.get("amount"),
                    date=r.get("date"),
                    pre_money_valuation=r.get("pre_money_valuation"),
                    post_money_valuation=r.get("post_money_valuation"),
                    lead_investor=r.get("lead_investor"),
                    other_investors=r.get("other_investors"),
                    filing_type="S-1",
                )
                for r in rounds_raw
            ]
    except Exception as e:
        logger.error(f"Claude S-1 parsing failed for {company_name}: {e}")

    return []


async def parse_10k_html(html_text: str, company_name: str) -> dict:
    """Parse 10-K filing HTML using Claude to extract financial metrics."""
    sections_to_find = [
        r"selected financial data",
        r"results of operations",
        r"financial statements",
        r"employees",
        r"business",
    ]

    extracted = _extract_html_sections(html_text, sections_to_find, max_chars=50000)
    if not extracted:
        extracted = html_text[:30000]

    system = """You are a financial document parser. Extract key financial metrics from SEC 10-K filings.

Return a JSON object with:
- revenue: latest annual revenue as string e.g. "$1.2B" (string or null)
- operating_income: as string (string or null)
- net_income: as string (string or null)
- employee_count: as string e.g. "5,000" (string or null)
- revenue_growth_yoy: year-over-year growth as string e.g. "25%" (string or null)

Return ONLY the JSON object, no other text."""

    user = f"Company: {company_name}\n\nExtracted 10-K sections:\n\n{extracted}"

    try:
        response = await _call_claude(system, user)
        import json
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
    except Exception as e:
        logger.error(f"Claude 10-K parsing failed for {company_name}: {e}")

    return {}


def _extract_html_sections(html: str, section_patterns: list[str], max_chars: int = 50000) -> str:
    """Extract named sections from HTML by heading patterns."""
    clean = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", clean)
    text = re.sub(r"\s+", " ", text).strip()

    extracted_parts = []
    for pattern in section_patterns:
        matches = list(re.finditer(pattern, text, re.IGNORECASE))
        for match in matches:
            start = max(0, match.start() - 100)
            end = min(len(text), match.end() + 8000)
            extracted_parts.append(text[start:end])

    combined = "\n\n---\n\n".join(extracted_parts)
    return combined[:max_chars]


async def verify_company_match(
    startup_name: str,
    startup_description: str | None,
    startup_website: str | None,
    startup_location: str | None,
    edgar_company: dict,
) -> bool:
    """Use Claude to verify if an EDGAR entity matches our startup."""
    system = "You are a company identity verification assistant. Determine if two company records refer to the same entity."

    user = f"""Our startup:
- Name: {startup_name}
- Description: {startup_description or 'N/A'}
- Website: {startup_website or 'N/A'}
- Location: {startup_location or 'N/A'}

SEC EDGAR entity:
- Name: {edgar_company.get('name', 'N/A')}
- State of incorporation: {edgar_company.get('state_of_incorporation', 'N/A')}
- SIC code: {edgar_company.get('sic', 'N/A')} ({edgar_company.get('sic_description', 'N/A')})
- Recent filings: {edgar_company.get('recent_filings', [])[:5]}

Are these the same company? Answer YES or NO with one sentence of reasoning."""

    try:
        response = await _call_claude(system, user)
        return response.strip().upper().startswith("YES")
    except Exception as e:
        logger.error(f"Claude verification failed for {startup_name}: {e}")
        return False


async def resolve_cik(
    db: AsyncSession,
    startup: Startup,
) -> str | None:
    """Resolve SEC CIK for a startup. Returns CIK string or None."""
    candidates = await edgar.search_company(startup.name)
    if not candidates:
        return None

    if len(candidates) > 1 and startup.location_state:
        state_matches = [c for c in candidates if c.state and c.state.upper() == startup.location_state.upper()]
        if state_matches:
            candidates = state_matches

    startup_location = None
    if startup.location_city and startup.location_state:
        startup_location = f"{startup.location_city}, {startup.location_state}"
    elif startup.location_city:
        startup_location = startup.location_city

    for candidate in candidates[:3]:
        company_info = await edgar.get_company_info(candidate.cik)
        is_match = await verify_company_match(
            startup_name=startup.name,
            startup_description=startup.description,
            startup_website=startup.website_url,
            startup_location=startup_location,
            edgar_company=company_info,
        )
        if is_match:
            return candidate.cik

    return None


def _parse_amount_to_float(amount_str: str | None) -> float | None:
    """Parse a dollar amount string like '$50M' or '$1.2B' to float."""
    if not amount_str:
        return None
    clean = amount_str.replace("~", "").replace("$", "").replace(",", "").strip()
    multiplier = 1
    if clean.upper().endswith("B"):
        multiplier = 1_000_000_000
        clean = clean[:-1]
    elif clean.upper().endswith("M"):
        multiplier = 1_000_000
        clean = clean[:-1]
    elif clean.upper().endswith("K"):
        multiplier = 1_000
        clean = clean[:-1]
    try:
        return float(clean) * multiplier
    except ValueError:
        return None


def _dates_within_days(date1: str | None, date2: str | None, days: int = 90) -> bool:
    """Check if two date strings (YYYY-MM-DD) are within N days of each other."""
    if not date1 or not date2:
        return False
    try:
        d1 = datetime.strptime(date1[:10], "%Y-%m-%d")
        d2 = datetime.strptime(date2[:10], "%Y-%m-%d")
        return abs((d1 - d2).days) <= days
    except ValueError:
        return False


def _amounts_within_tolerance(a1: float | None, a2: float | None, tolerance: float = 0.2) -> bool:
    """Check if two amounts are within tolerance % of each other."""
    if a1 is None or a2 is None or a1 == 0:
        return False
    return abs(a1 - a2) / max(a1, a2) <= tolerance


async def merge_funding_round(
    db: AsyncSession,
    startup_id: str,
    edgar_round: FundingRoundData,
) -> dict:
    """Merge an EDGAR-extracted funding round into existing startup data.

    Match by: date within 90 days + amount within 20%.
    EDGAR wins for: amount, pre/post_money_valuation, date.
    Perplexity wins for: lead_investor, other_investors, round_name.
    """
    result = await db.execute(
        select(StartupFundingRound)
        .where(StartupFundingRound.startup_id == startup_id)
    )
    existing_rounds = result.scalars().all()

    edgar_amount = _parse_amount_to_float(edgar_round.amount)

    best_match = None
    for existing in existing_rounds:
        existing_amount = _parse_amount_to_float(existing.amount)

        date_match = _dates_within_days(edgar_round.date, existing.date)
        amount_match = _amounts_within_tolerance(edgar_amount, existing_amount)

        if date_match and amount_match:
            best_match = existing
            break
        if date_match and edgar_amount and existing_amount:
            best_match = existing

    if best_match:
        if edgar_round.amount:
            best_match.amount = edgar_round.amount
        if edgar_round.date:
            best_match.date = edgar_round.date
        if edgar_round.pre_money_valuation:
            best_match.pre_money_valuation = edgar_round.pre_money_valuation
        if edgar_round.post_money_valuation:
            best_match.post_money_valuation = edgar_round.post_money_valuation
        if not best_match.round_name and edgar_round.round_name:
            best_match.round_name = edgar_round.round_name
        if not best_match.lead_investor and edgar_round.lead_investor:
            best_match.lead_investor = edgar_round.lead_investor
        if not best_match.other_investors and edgar_round.other_investors:
            best_match.other_investors = edgar_round.other_investors
        best_match.data_source = "edgar"
        return {"action": "updated", "round_name": best_match.round_name}

    if edgar_round.amount:
        max_order = max((r.sort_order for r in existing_rounds), default=-1)
        new_round = StartupFundingRound(
            startup_id=startup_id,
            round_name=edgar_round.round_name or f"Form D ({edgar_round.date or 'undated'})",
            amount=edgar_round.amount,
            date=edgar_round.date,
            pre_money_valuation=edgar_round.pre_money_valuation,
            post_money_valuation=edgar_round.post_money_valuation,
            lead_investor=edgar_round.lead_investor,
            other_investors=edgar_round.other_investors,
            sort_order=max_order + 1,
            data_source="edgar",
        )
        db.add(new_round)
        return {"action": "created", "round_name": new_round.round_name}

    return {"action": "skipped", "reason": "no amount"}
