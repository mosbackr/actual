"""Seed default due diligence templates."""
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.industry import Base
from app.models.template import DueDiligenceTemplate, TemplateDimension
from app.utils import slugify

TEMPLATES = {
    "SaaS": {
        "description": "Software-as-a-Service startup evaluation",
        "dimensions": [
            ("Market Size", 1.5),
            ("Product-Market Fit", 2.0),
            ("Revenue Model", 1.5),
            ("Technical Moat", 1.0),
            ("Team Strength", 1.5),
            ("Scalability", 1.0),
            ("Customer Acquisition", 1.0),
            ("Churn & Retention", 1.5),
        ],
    },
    "BioTech": {
        "description": "Biotech and life sciences startup evaluation",
        "dimensions": [
            ("Regulatory Path", 2.0),
            ("Clinical Pipeline", 2.0),
            ("IP Portfolio", 1.5),
            ("Market Size", 1.0),
            ("Team Credentials", 1.5),
            ("Funding Runway", 1.0),
            ("Scientific Validity", 2.0),
        ],
    },
    "FinTech": {
        "description": "Financial technology startup evaluation",
        "dimensions": [
            ("Regulatory Compliance", 2.0),
            ("Market Fit", 1.5),
            ("Security & Trust", 2.0),
            ("Unit Economics", 1.5),
            ("Scalability", 1.0),
            ("Team & Domain Expertise", 1.5),
            ("Competitive Landscape", 1.0),
        ],
    },
    "General": {
        "description": "General startup evaluation template",
        "dimensions": [
            ("Market Size", 1.0),
            ("Product-Market Fit", 1.5),
            ("Team Strength", 1.5),
            ("Business Model", 1.0),
            ("Competitive Advantage", 1.0),
            ("Traction", 1.0),
            ("Scalability", 1.0),
        ],
    },
}


async def seed_templates():
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        for name, config in TEMPLATES.items():
            template = DueDiligenceTemplate(
                name=name,
                slug=slugify(name),
                description=config["description"],
            )
            session.add(template)
            await session.flush()

            for i, (dim_name, weight) in enumerate(config["dimensions"]):
                session.add(TemplateDimension(
                    template_id=template.id,
                    dimension_name=dim_name,
                    dimension_slug=slugify(dim_name),
                    weight=weight,
                    sort_order=i,
                ))

        await session.commit()
        print(f"Seeded {len(TEMPLATES)} DD templates.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_templates())
