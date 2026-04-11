import re
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.startup import Startup


_STRIP_SUFFIXES = re.compile(
    r"\b(inc\.?|ltd\.?|llc|co\.?|corp\.?|corporation|gmbh|pty|limited)\b",
    re.IGNORECASE,
)


def normalize_name(name: str) -> str:
    """Normalize a startup name for dedup comparison."""
    result = name.lower().strip()
    result = _STRIP_SUFFIXES.sub("", result)
    result = re.sub(r"[^\w\s]", "", result)
    result = re.sub(r"\s+", " ", result).strip()
    return result


def normalize_domain(url: str) -> str:
    """Extract and normalize domain from a URL for dedup comparison."""
    if not url:
        return ""
    if "://" not in url:
        url = f"https://{url}"
    try:
        parsed = urlparse(url)
        domain = (parsed.hostname or "").lower()
        domain = re.sub(r"^www\.", "", domain)
        return domain
    except Exception:
        return ""


async def find_duplicate(
    db: AsyncSession,
    name: str,
    website_url: str | None = None,
    exclude_id: str | None = None,
) -> dict | None:
    """Check if a startup with the same normalized name or domain exists.
    Returns a dict with id, name, status if found, None otherwise.
    """
    norm_name = normalize_name(name)
    norm_domain = normalize_domain(website_url) if website_url else ""

    result = await db.execute(select(Startup))
    startups = result.scalars().all()

    for s in startups:
        if exclude_id and str(s.id) == exclude_id:
            continue
        if normalize_name(s.name) == norm_name:
            return {"id": str(s.id), "name": s.name, "status": s.status.value}
        if norm_domain and s.website_url and normalize_domain(s.website_url) == norm_domain:
            return {"id": str(s.id), "name": s.name, "status": s.status.value}

    return None
