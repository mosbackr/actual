"""Seed due diligence templates by industry and stage."""
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.industry import Base
from app.models.template import DueDiligenceTemplate, TemplateDimension
from app.utils import slugify

# ---------------------------------------------------------------------------
# Templates organized by industry (stage=None means all stages)
# ---------------------------------------------------------------------------

TEMPLATES = [
    # -----------------------------------------------------------------------
    # INDUSTRY-SPECIFIC TEMPLATES
    # -----------------------------------------------------------------------
    {
        "name": "SaaS",
        "industry_slug": "saas",
        "stage": None,
        "description": "Software-as-a-Service company evaluation",
        "dimensions": [
            ("Product-Market Fit", 2.0),
            ("Revenue Model & Unit Economics", 1.5),
            ("Market Size & TAM", 1.5),
            ("Team Strength", 1.5),
            ("Technical Moat & Architecture", 1.0),
            ("Scalability", 1.0),
            ("Customer Acquisition & CAC", 1.0),
            ("Churn & Retention", 1.5),
        ],
    },
    {
        "name": "Fintech",
        "industry_slug": "fintech",
        "stage": None,
        "description": "Financial technology company evaluation",
        "dimensions": [
            ("Regulatory Compliance", 2.0),
            ("Security & Trust Infrastructure", 2.0),
            ("Market Fit & Distribution", 1.5),
            ("Unit Economics", 1.5),
            ("Team & Domain Expertise", 1.5),
            ("Competitive Landscape", 1.0),
            ("Scalability & Infrastructure", 1.0),
            ("Partnerships & Integration", 1.0),
        ],
    },
    {
        "name": "Healthcare",
        "industry_slug": "healthcare",
        "stage": None,
        "description": "Healthcare and health tech company evaluation",
        "dimensions": [
            ("Regulatory & Compliance Path", 2.0),
            ("Clinical Evidence & Validation", 2.0),
            ("Market Size & Payer Landscape", 1.5),
            ("Team Credentials & Advisors", 1.5),
            ("Patient/Provider Adoption", 1.5),
            ("Reimbursement Strategy", 1.0),
            ("Data Privacy & Security", 1.0),
            ("Competitive Differentiation", 1.0),
        ],
    },
    {
        "name": "BioTech",
        "industry_slug": "biotech",
        "stage": None,
        "description": "Biotechnology and life sciences evaluation",
        "dimensions": [
            ("Scientific Validity", 2.0),
            ("Clinical Pipeline & Stage", 2.0),
            ("Regulatory Path (FDA/EMA)", 2.0),
            ("IP Portfolio & Freedom to Operate", 1.5),
            ("Team Credentials", 1.5),
            ("Market Size & Indication", 1.0),
            ("Funding Runway & Capital Needs", 1.0),
            ("Manufacturing & Scale-up", 0.8),
        ],
    },
    {
        "name": "AI/ML",
        "industry_slug": "ai-ml",
        "stage": None,
        "description": "Artificial intelligence and machine learning evaluation",
        "dimensions": [
            ("Technical Moat & Model Quality", 2.0),
            ("Data Advantage & Pipeline", 2.0),
            ("Product-Market Fit", 1.5),
            ("Team & Research Talent", 1.5),
            ("Market Size & TAM", 1.0),
            ("Scalability & Inference Costs", 1.0),
            ("Competitive Landscape", 1.0),
            ("Ethical AI & Governance", 0.8),
        ],
    },
    {
        "name": "Cybersecurity",
        "industry_slug": "cybersecurity",
        "stage": None,
        "description": "Cybersecurity company evaluation",
        "dimensions": [
            ("Technical Depth & Detection Capability", 2.0),
            ("Threat Intelligence & Differentiation", 1.5),
            ("Market Fit & ICP Clarity", 1.5),
            ("Team & Domain Expertise", 1.5),
            ("Compliance & Certifications", 1.5),
            ("Platform vs Point Solution", 1.0),
            ("Go-to-Market & Sales Motion", 1.0),
            ("Retention & Expansion", 1.0),
        ],
    },
    {
        "name": "E-Commerce",
        "industry_slug": "e-commerce",
        "stage": None,
        "description": "E-commerce and direct-to-consumer evaluation",
        "dimensions": [
            ("Brand & Customer Loyalty", 1.5),
            ("Unit Economics & Margins", 2.0),
            ("Supply Chain & Fulfillment", 1.5),
            ("Customer Acquisition & CAC", 1.5),
            ("Market Size & Category", 1.0),
            ("Team & Operations", 1.0),
            ("Competitive Differentiation", 1.0),
            ("Repeat Purchase & LTV", 1.5),
        ],
    },
    {
        "name": "CleanTech",
        "industry_slug": "cleantech",
        "stage": None,
        "description": "Clean technology and climate evaluation",
        "dimensions": [
            ("Technology Readiness & Scalability", 2.0),
            ("Market Size & Policy Tailwinds", 1.5),
            ("Regulatory & Permitting Path", 1.5),
            ("Unit Economics & Cost Curve", 1.5),
            ("Team & Technical Depth", 1.5),
            ("Carbon Impact & ESG Metrics", 1.0),
            ("Capital Efficiency", 1.0),
            ("Partnerships & Offtake", 1.0),
        ],
    },
    {
        "name": "EdTech",
        "industry_slug": "edtech",
        "stage": None,
        "description": "Education technology evaluation",
        "dimensions": [
            ("Learning Outcomes & Efficacy", 2.0),
            ("Product-Market Fit", 1.5),
            ("User Engagement & Retention", 1.5),
            ("Market Size & Segment", 1.0),
            ("Team & Domain Expertise", 1.5),
            ("Go-to-Market (B2B vs B2C)", 1.0),
            ("Content & Curriculum Quality", 1.0),
            ("Revenue Model & Pricing", 1.0),
        ],
    },
    {
        "name": "Logistics",
        "industry_slug": "logistics",
        "stage": None,
        "description": "Logistics and supply chain evaluation",
        "dimensions": [
            ("Operational Efficiency & Cost Savings", 2.0),
            ("Technology & Automation", 1.5),
            ("Network Effects & Scale", 1.5),
            ("Market Size & Segment", 1.0),
            ("Team & Operations Expertise", 1.5),
            ("Unit Economics", 1.0),
            ("Competitive Landscape", 1.0),
            ("Regulatory & Compliance", 0.8),
        ],
    },
    {
        "name": "Enterprise Software",
        "industry_slug": "enterprise-software",
        "stage": None,
        "description": "Enterprise software and B2B platform evaluation",
        "dimensions": [
            ("Product-Market Fit & ICP", 2.0),
            ("Revenue Model & Net Retention", 1.5),
            ("Technical Moat & Architecture", 1.5),
            ("Market Size & TAM", 1.0),
            ("Team & Go-to-Market", 1.5),
            ("Competitive Landscape", 1.0),
            ("Integration & Ecosystem", 1.0),
            ("Scalability", 1.0),
        ],
    },
    {
        "name": "Consumer Apps",
        "industry_slug": "consumer-apps",
        "stage": None,
        "description": "Consumer application evaluation",
        "dimensions": [
            ("User Growth & Engagement", 2.0),
            ("Retention & DAU/MAU", 2.0),
            ("Product Uniqueness & UX", 1.5),
            ("Market Size & TAM", 1.0),
            ("Monetization Strategy", 1.0),
            ("Team & Product Vision", 1.5),
            ("Virality & Network Effects", 1.0),
            ("Competitive Landscape", 0.8),
        ],
    },
    {
        "name": "PropTech",
        "industry_slug": "proptech",
        "stage": None,
        "description": "Property technology evaluation",
        "dimensions": [
            ("Market Fit & Distribution", 1.5),
            ("Regulatory & Compliance", 1.5),
            ("Technology & Data Advantage", 1.5),
            ("Unit Economics", 1.5),
            ("Team & Industry Expertise", 1.5),
            ("Market Size & Segment", 1.0),
            ("Competitive Landscape", 1.0),
            ("Scalability & Geography", 1.0),
        ],
    },
    {
        "name": "InsurTech",
        "industry_slug": "insurtech",
        "stage": None,
        "description": "Insurance technology evaluation",
        "dimensions": [
            ("Regulatory & Licensing", 2.0),
            ("Underwriting & Risk Models", 2.0),
            ("Distribution & Customer Acquisition", 1.5),
            ("Claims Efficiency", 1.0),
            ("Team & Domain Expertise", 1.5),
            ("Market Size & Segment", 1.0),
            ("Technology & Data Advantage", 1.0),
            ("Capital Requirements & Reinsurance", 1.0),
        ],
    },
    {
        "name": "Robotics",
        "industry_slug": "robotics",
        "stage": None,
        "description": "Robotics and automation evaluation",
        "dimensions": [
            ("Technology Readiness Level", 2.0),
            ("Hardware-Software Integration", 1.5),
            ("Market Fit & Use Case Clarity", 1.5),
            ("Unit Economics & COGS", 1.5),
            ("Team & Technical Depth", 1.5),
            ("Manufacturing & Scale-up", 1.0),
            ("Safety & Regulatory", 1.0),
            ("Competitive Landscape", 0.8),
        ],
    },
    {
        "name": "SpaceTech",
        "industry_slug": "spacetech",
        "stage": None,
        "description": "Space technology evaluation",
        "dimensions": [
            ("Technology Readiness & Heritage", 2.0),
            ("Market Size & Customer Pipeline", 1.5),
            ("Team Credentials & Track Record", 2.0),
            ("Capital Efficiency & Burn Rate", 1.5),
            ("Regulatory & Launch Access", 1.0),
            ("Competitive Landscape", 1.0),
            ("IP & Technical Moat", 1.0),
            ("Government Contracts & Revenue", 1.0),
        ],
    },
    {
        "name": "Gaming",
        "industry_slug": "gaming",
        "stage": None,
        "description": "Gaming and interactive entertainment evaluation",
        "dimensions": [
            ("Gameplay & User Engagement", 2.0),
            ("Monetization & Revenue Model", 1.5),
            ("Team & Creative Track Record", 1.5),
            ("Market Size & Genre Fit", 1.0),
            ("Technology & Engine", 1.0),
            ("Community & Retention", 1.5),
            ("IP & Franchise Potential", 1.0),
            ("Distribution & Platform Strategy", 1.0),
        ],
    },
    {
        "name": "FoodTech",
        "industry_slug": "foodtech",
        "stage": None,
        "description": "Food technology evaluation",
        "dimensions": [
            ("Product & Taste / Quality", 1.5),
            ("Market Size & Segment", 1.0),
            ("Supply Chain & Manufacturing", 1.5),
            ("Unit Economics & Margins", 1.5),
            ("Regulatory & Food Safety", 1.5),
            ("Team & Domain Expertise", 1.5),
            ("Distribution & Retail Strategy", 1.0),
            ("Sustainability & Impact", 1.0),
        ],
    },
    {
        "name": "AgTech",
        "industry_slug": "agtech",
        "stage": None,
        "description": "Agricultural technology evaluation",
        "dimensions": [
            ("Technology & Yield Impact", 2.0),
            ("Market Size & Crop Segment", 1.0),
            ("Farmer Adoption & Distribution", 1.5),
            ("Unit Economics & ROI for Farmer", 1.5),
            ("Regulatory & Environmental", 1.0),
            ("Team & Agriculture Expertise", 1.5),
            ("Data & Precision Agriculture", 1.0),
            ("Scalability & Geography", 1.0),
        ],
    },
    {
        "name": "Media",
        "industry_slug": "media",
        "stage": None,
        "description": "Media and content platform evaluation",
        "dimensions": [
            ("Content Quality & Differentiation", 2.0),
            ("Audience Growth & Engagement", 1.5),
            ("Monetization Strategy", 1.5),
            ("Market Size & Segment", 1.0),
            ("Team & Creative Vision", 1.5),
            ("Distribution & Platform Strategy", 1.0),
            ("Retention & Stickiness", 1.0),
            ("Competitive Landscape", 0.8),
        ],
    },
    # -----------------------------------------------------------------------
    # STAGE-SPECIFIC TEMPLATES (applies across industries)
    # -----------------------------------------------------------------------
    {
        "name": "Pre-Seed / Idea Stage",
        "industry_slug": None,
        "stage": "pre_seed",
        "description": "Early idea-stage evaluation — emphasis on team, vision, and market",
        "dimensions": [
            ("Founder-Market Fit", 2.0),
            ("Team Strength & Complementarity", 2.0),
            ("Market Opportunity & Timing", 1.5),
            ("Problem Clarity & Urgency", 1.5),
            ("Initial Traction / Signals", 1.0),
            ("Vision & Ambition", 1.0),
            ("Capital Efficiency Plan", 0.8),
        ],
    },
    {
        "name": "Seed Stage",
        "industry_slug": None,
        "stage": "seed",
        "description": "Seed stage evaluation — early product, initial traction",
        "dimensions": [
            ("Team Strength & Execution", 2.0),
            ("Product-Market Fit Signals", 2.0),
            ("Market Size & Opportunity", 1.5),
            ("Early Traction & Metrics", 1.5),
            ("Business Model Clarity", 1.0),
            ("Competitive Positioning", 1.0),
            ("Capital Efficiency", 1.0),
            ("Technical Foundation", 0.8),
        ],
    },
    {
        "name": "Series A",
        "industry_slug": None,
        "stage": "series_a",
        "description": "Series A evaluation — proven PMF, scaling revenue",
        "dimensions": [
            ("Product-Market Fit Evidence", 2.0),
            ("Revenue Growth & Trajectory", 2.0),
            ("Unit Economics & Margins", 1.5),
            ("Market Size & Expansion", 1.5),
            ("Team & Organizational Scaling", 1.5),
            ("Go-to-Market Repeatability", 1.0),
            ("Competitive Moat", 1.0),
            ("Capital Efficiency", 0.8),
        ],
    },
    {
        "name": "Series B+",
        "industry_slug": None,
        "stage": "series_b",
        "description": "Growth stage evaluation — scaling operations",
        "dimensions": [
            ("Revenue Scale & Growth Rate", 2.0),
            ("Unit Economics & Path to Profitability", 2.0),
            ("Market Leadership & Share", 1.5),
            ("Organizational Maturity", 1.5),
            ("Competitive Moat & Defensibility", 1.5),
            ("Expansion Strategy (New Markets/Products)", 1.0),
            ("Management Team Depth", 1.0),
            ("Operational Excellence", 1.0),
        ],
    },
    {
        "name": "Growth / Late Stage",
        "industry_slug": None,
        "stage": "growth",
        "description": "Late stage / pre-IPO evaluation",
        "dimensions": [
            ("Revenue & Profitability Metrics", 2.0),
            ("Market Position & Dominance", 2.0),
            ("Financial Health & Predictability", 1.5),
            ("Management Team & Governance", 1.5),
            ("Competitive Moat & Defensibility", 1.5),
            ("Expansion & International Growth", 1.0),
            ("IPO/Exit Readiness", 1.0),
            ("Risk Factors & Concentration", 1.0),
        ],
    },
    # -----------------------------------------------------------------------
    # GENERAL FALLBACK
    # -----------------------------------------------------------------------
    {
        "name": "General",
        "industry_slug": None,
        "stage": None,
        "description": "General-purpose startup evaluation template",
        "dimensions": [
            ("Market Opportunity", 1.2),
            ("Team Strength", 1.3),
            ("Product & Technology", 1.1),
            ("Traction & Metrics", 1.2),
            ("Business Model", 1.0),
            ("Competitive Moat", 1.0),
            ("Financials & Unit Economics", 0.9),
            ("Timing & Market Readiness", 0.8),
        ],
    },
]


async def seed_templates():
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # Check if templates already exist — skip if so
        result = await session.execute(select(DueDiligenceTemplate).limit(1))
        if result.scalar_one_or_none() is not None:
            print("Templates already exist, skipping seed.")
            await engine.dispose()
            return

        for t in TEMPLATES:
            template = DueDiligenceTemplate(
                name=t["name"],
                slug=slugify(t["name"]),
                description=t["description"],
                industry_slug=t["industry_slug"],
                stage=t["stage"],
            )
            session.add(template)
            await session.flush()

            for i, (dim_name, weight) in enumerate(t["dimensions"]):
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
