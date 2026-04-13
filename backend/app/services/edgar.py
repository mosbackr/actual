"""EDGAR HTTP client — talks to SEC EDGAR REST APIs.

Pure HTTP, no business logic. Handles rate limiting (150ms between requests).
SEC requires User-Agent header with company name and email.
"""
import asyncio
import logging
from dataclasses import dataclass

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# SEC asks for max 10 req/s; we use 150ms delay to be safe
_RATE_LIMIT_DELAY = 0.15
_last_request_time = 0.0


def _headers() -> dict[str, str]:
    return {
        "User-Agent": settings.edgar_user_agent,
        "Accept": "application/json",
    }


async def _rate_limited_get(url: str, accept: str = "application/json") -> httpx.Response:
    """GET with rate limiting. Raises on non-2xx."""
    global _last_request_time
    now = asyncio.get_event_loop().time()
    elapsed = now - _last_request_time
    if elapsed < _RATE_LIMIT_DELAY:
        await asyncio.sleep(_RATE_LIMIT_DELAY - elapsed)
    _last_request_time = asyncio.get_event_loop().time()

    headers = _headers()
    headers["Accept"] = accept

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp


@dataclass
class EdgarCompany:
    """A company result from EDGAR search."""
    name: str
    cik: str
    state: str | None
    sic: str | None
    sic_description: str | None


@dataclass
class EdgarFiling:
    """A filing from the EDGAR filing index."""
    accession_number: str
    filing_type: str
    filing_date: str
    primary_document: str
    description: str


@dataclass
class EdgarFormDHit:
    """A Form D filing hit from EDGAR EFTS search."""
    accession_number: str
    entity_name: str
    file_date: str
    file_num: str | None
    cik: str | None


async def search_company(name: str) -> list[EdgarCompany]:
    """Search EDGAR for companies matching the given name.

    Returns a list of EdgarCompany results with CIK numbers.
    Uses the EDGAR company search Atom feed.
    """
    import xml.etree.ElementTree as ET
    from urllib.parse import quote

    encoded_name = quote(name)
    url = f"https://www.sec.gov/cgi-bin/browse-edgar?company={encoded_name}&CIK=&type=&dateb=&owner=include&count=40&search_text=&action=getcompany&output=atom"

    try:
        resp = await _rate_limited_get(url, accept="application/atom+xml")
    except httpx.HTTPStatusError as e:
        logger.warning(f"EDGAR company search failed for '{name}': {e}")
        return []

    root = ET.fromstring(resp.text)
    ns = {"atom": "http://www.w3.org/2005/Atom", "edgar": "http://www.sec.gov/cgi-bin/browse-edgar"}

    results = []
    for entry in root.findall("atom:entry", ns):
        content = entry.find("atom:content", ns)
        if content is None:
            continue

        cik_el = content.find(".//edgar:cik", ns)
        name_el = content.find(".//edgar:conformed-name", ns)
        state_el = content.find(".//edgar:state", ns)
        sic_el = content.find(".//edgar:assigned-sic", ns)
        sic_desc_el = content.find(".//edgar:assigned-sic-desc", ns)

        if cik_el is not None and name_el is not None:
            results.append(EdgarCompany(
                name=name_el.text or "",
                cik=cik_el.text or "",
                state=state_el.text if state_el is not None else None,
                sic=sic_el.text if sic_el is not None else None,
                sic_description=sic_desc_el.text if sic_desc_el is not None else None,
            ))

    return results


async def get_filings(cik: str) -> list[EdgarFiling]:
    """Get all filings for a CIK number.

    Returns filings sorted by date (newest first). Filters to Form D, S-1, 10-K.
    """
    padded_cik = cik.zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{padded_cik}.json"

    try:
        resp = await _rate_limited_get(url)
    except httpx.HTTPStatusError as e:
        logger.warning(f"EDGAR filings fetch failed for CIK {cik}: {e}")
        return []

    data = resp.json()
    recent = data.get("filings", {}).get("recent", {})

    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])
    descriptions = recent.get("primaryDocDescription", [])

    target_forms = {"D", "D/A", "S-1", "S-1/A", "10-K", "10-K/A"}

    filings = []
    for i in range(len(forms)):
        if forms[i] in target_forms:
            filings.append(EdgarFiling(
                accession_number=accessions[i] if i < len(accessions) else "",
                filing_type=forms[i],
                filing_date=dates[i] if i < len(dates) else "",
                primary_document=primary_docs[i] if i < len(primary_docs) else "",
                description=descriptions[i] if i < len(descriptions) else "",
            ))

    return filings


async def download_filing(cik: str, accession_number: str, document: str) -> str:
    """Download a filing document (XML for Form D, HTML for S-1/10-K).

    Returns the raw document text.
    """
    accession_path = accession_number.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_path}/{document}"

    resp = await _rate_limited_get(url, accept="*/*")
    return resp.text


async def get_company_info(cik: str) -> dict:
    """Get basic company info for a CIK (name, SIC, state, recent filings summary).

    Used for Claude verification during company matching.
    """
    padded_cik = cik.zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{padded_cik}.json"

    try:
        resp = await _rate_limited_get(url)
    except httpx.HTTPStatusError:
        return {}

    data = resp.json()
    recent = data.get("filings", {}).get("recent", {})
    recent_forms = recent.get("form", [])[:10]
    recent_dates = recent.get("filingDate", [])[:10]

    return {
        "name": data.get("name", ""),
        "cik": cik,
        "sic": data.get("sic", ""),
        "sic_description": data.get("sicDescription", ""),
        "state_of_incorporation": data.get("stateOfIncorporation", ""),
        "state": data.get("addresses", {}).get("business", {}).get("stateOrCountry", ""),
        "recent_filings": [
            {"form": recent_forms[i], "date": recent_dates[i]}
            for i in range(min(len(recent_forms), len(recent_dates)))
        ],
    }


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


async def get_cik_from_accession(accession_number: str) -> str | None:
    """Resolve CIK from an accession number using the EDGAR filing index."""
    # The accession number format is XXXXXXXXXX-YY-ZZZZZZ where X is CIK
    parts = accession_number.split("-")
    if len(parts) >= 1:
        potential_cik = parts[0].lstrip("0")
        if potential_cik.isdigit():
            return potential_cik

    return None
