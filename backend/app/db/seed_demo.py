"""Seed demo startups and industries."""
import asyncio

from sqlalchemy import select

from app.db.session import async_session as AsyncSessionLocal
from app.models.industry import Industry
from app.models.startup import Startup, StartupStage, StartupStatus


INDUSTRIES = ["Fintech", "Healthcare", "AI/ML", "SaaS", "E-commerce", "Climate", "Cybersecurity", "Edtech"]

STARTUPS = [
    {
        "name": "Meridian Finance",
        "slug": "meridian-finance",
        "description": "AI-powered credit underwriting for emerging markets. Using alternative data and machine learning to assess creditworthiness where traditional scoring fails.",
        "stage": "series_a",
        "status": "approved",
        "ai_score": 78,
        "expert_score": 72,
        "user_score": 68,
        "industries": ["Fintech", "AI/ML"],
        "location_country": "US",
        "location_city": "San Francisco",
        "location_state": "CA",
    },
    {
        "name": "Curation Health",
        "slug": "curation-health",
        "description": "Clinical decision support platform that aggregates patient data across fragmented health systems. Reduces diagnostic errors by 40% in pilot studies.",
        "stage": "seed",
        "status": "approved",
        "ai_score": 82,
        "expert_score": None,
        "user_score": None,
        "industries": ["Healthcare", "AI/ML"],
        "location_country": "US",
        "location_city": "Boston",
        "location_state": "MA",
    },
    {
        "name": "Carbonsync",
        "slug": "carbonsync",
        "description": "Carbon credit marketplace with satellite-verified offsets. Enterprise clients can purchase, trade, and retire credits with full chain-of-custody transparency.",
        "stage": "series_b",
        "status": "approved",
        "ai_score": 65,
        "expert_score": 71,
        "user_score": 58,
        "industries": ["Climate", "SaaS"],
        "location_country": "UK",
        "location_city": "London",
        "location_state": None,
    },
    {
        "name": "Patchwork Security",
        "slug": "patchwork-security",
        "description": "Automated vulnerability remediation for cloud-native infrastructure. Detects, prioritizes, and patches security issues across Kubernetes clusters without downtime.",
        "stage": "series_a",
        "status": "approved",
        "ai_score": 88,
        "expert_score": 85,
        "user_score": 79,
        "industries": ["Cybersecurity", "SaaS"],
        "location_country": "US",
        "location_city": "Austin",
        "location_state": "TX",
    },
    {
        "name": "Learnwell",
        "slug": "learnwell",
        "description": "Adaptive learning platform for K-12 that personalizes curriculum pacing based on individual student comprehension patterns.",
        "stage": "pre_seed",
        "status": "approved",
        "ai_score": 45,
        "expert_score": None,
        "user_score": 52,
        "industries": ["Edtech", "AI/ML"],
        "location_country": "US",
        "location_city": "New York",
        "location_state": "NY",
    },
    {
        "name": "Vaultline",
        "slug": "vaultline",
        "description": "Embedded banking infrastructure for B2B SaaS platforms. Enables any software company to offer payments, lending, and treasury management to their customers.",
        "stage": "series_a",
        "status": "approved",
        "ai_score": 74,
        "expert_score": 69,
        "user_score": 71,
        "industries": ["Fintech", "SaaS"],
        "location_country": "US",
        "location_city": "New York",
        "location_state": "NY",
    },
    {
        "name": "Greenloop",
        "slug": "greenloop",
        "description": "Circular economy logistics platform. Manages reverse supply chains for consumer electronics, tracking devices from end-of-life through refurbishment or recycling.",
        "stage": "seed",
        "status": "pending",
        "ai_score": 55,
        "expert_score": None,
        "user_score": None,
        "industries": ["Climate", "E-commerce"],
        "location_country": "DE",
        "location_city": "Berlin",
        "location_state": None,
    },
    {
        "name": "Nextera Diagnostics",
        "slug": "nextera-diagnostics",
        "description": "Point-of-care blood testing device that delivers lab-grade results in under 10 minutes. Currently seeking FDA clearance for 12 biomarkers.",
        "stage": "series_a",
        "status": "pending",
        "ai_score": 71,
        "expert_score": None,
        "user_score": None,
        "industries": ["Healthcare"],
        "location_country": "US",
        "location_city": "San Diego",
        "location_state": "CA",
    },
]


async def seed_demo():
    async with AsyncSessionLocal() as session:
        # Create industries
        industry_map: dict[str, Industry] = {}
        for name in INDUSTRIES:
            slug = name.lower().replace("/", "-").replace(" ", "-")
            result = await session.execute(select(Industry).where(Industry.slug == slug))
            ind = result.scalar_one_or_none()
            if ind is None:
                ind = Industry(name=name, slug=slug)
                session.add(ind)
                await session.flush()
            industry_map[name] = ind

        # Create startups
        created = 0
        for data in STARTUPS:
            result = await session.execute(select(Startup).where(Startup.slug == data["slug"]))
            if result.scalar_one_or_none() is not None:
                continue

            startup = Startup(
                name=data["name"],
                slug=data["slug"],
                description=data["description"],
                stage=StartupStage(data["stage"]),
                status=StartupStatus(data["status"]),
                ai_score=data["ai_score"],
                expert_score=data["expert_score"],
                user_score=data["user_score"],
                location_country=data["location_country"],
                location_city=data["location_city"],
                location_state=data["location_state"],
            )
            for ind_name in data["industries"]:
                startup.industries.append(industry_map[ind_name])
            session.add(startup)
            created += 1

        await session.commit()
        print(f"Seeded {created} startups and {len(INDUSTRIES)} industries")


if __name__ == "__main__":
    asyncio.run(seed_demo())
