import asyncio

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.config import settings
from app.models.industry import Industry
from app.models.skill import Skill

INDUSTRIES = [
    "Fintech", "Healthcare", "EdTech", "CleanTech", "SaaS", "E-Commerce",
    "Logistics", "AI/ML", "Cybersecurity", "BioTech", "PropTech", "InsurTech",
    "FoodTech", "AgTech", "SpaceTech", "Robotics", "Gaming", "Media",
    "Enterprise Software", "Consumer Apps",
]

SKILLS = [
    "Go-to-Market Strategy", "Technical Architecture", "Regulatory Compliance",
    "Financial Modeling", "Product-Market Fit", "Team Assessment",
    "Competitive Analysis", "IP & Moat Evaluation", "Sales & Traction Analysis",
    "Market Sizing", "Unit Economics", "Supply Chain",
]


def _slugify(name: str) -> str:
    return name.lower().replace("/", "-").replace(" & ", "-").replace(" ", "-")


async def seed():
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        for name in INDUSTRIES:
            session.add(Industry(name=name, slug=_slugify(name)))
        for name in SKILLS:
            session.add(Skill(name=name, slug=_slugify(name)))
        await session.commit()
    await engine.dispose()
    print(f"Seeded {len(INDUSTRIES)} industries and {len(SKILLS)} skills.")


if __name__ == "__main__":
    asyncio.run(seed())
