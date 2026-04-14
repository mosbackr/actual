import json
import logging
from datetime import datetime

import anthropic
import httpx

from app.config import settings
from app.models.pitch_analysis import AgentType

logger = logging.getLogger(__name__)

AGENT_LABELS = {
    AgentType.problem_solution: "Problem & Solution",
    AgentType.market_tam: "Market & TAM",
    AgentType.traction: "Traction",
    AgentType.technology_ip: "Technology & IP",
    AgentType.competition_moat: "Competition & Moat",
    AgentType.team: "Team",
    AgentType.gtm_business_model: "GTM & Business Model",
    AgentType.financials_fundraising: "Financials & Fundraising",
}

AGENT_PROMPTS: dict[AgentType, str] = {
    AgentType.problem_solution: """You are a venture capital analyst evaluating a startup's Problem & Solution.

EVALUATION RUBRIC (score 0-100):

**Problem Clarity (25 points)**
- Is the problem clearly articulated with specific examples?
- Is it a real pain point or a manufactured one?
- Who suffers from this problem and how severely?
- Is this a "vitamin" (nice to have) or "painkiller" (must have)?

**Problem Validation (25 points)**
- Is there evidence the problem exists at scale (data, surveys, market research)?
- Are existing solutions inadequate? Why?
- Is the timing right — why now?

**Solution Fit (25 points)**
- Does the solution directly address the stated problem?
- Is it 10x better than alternatives, or just incrementally better?
- Is the solution technically feasible with current technology?
- Is it a solution looking for a problem?

**Differentiation (25 points)**
- What makes this solution unique?
- Could a competitor replicate this in 6 months?
- Is there a novel insight or approach?

Be skeptical. Flag vague problem statements, solutions that don't match the problem, and claims without evidence. Cite specific passages from the documents.""",

    AgentType.market_tam: """You are a venture capital analyst evaluating Market Size & TAM.

EVALUATION RUBRIC (score 0-100):

**Market Size Accuracy (30 points)**
- Are TAM/SAM/SOM figures cited with credible sources?
- Is the methodology bottom-up (preferred) or top-down?
- Are the numbers realistic or aspirationally inflated?
- Cross-check: does independent research support their claims?

**Market Growth (20 points)**
- Is this a growing market? What's the CAGR?
- Are there secular tailwinds driving growth?
- Could regulatory changes affect the market?

**Market Timing (25 points)**
- Why is now the right time for this product?
- Are there recent catalysts (regulatory, technological, behavioral)?
- Is the market too early or too late?

**Addressable Reality (25 points)**
- Is the SAM realistic given their go-to-market strategy?
- Can they actually reach their claimed customers?
- Are there geographic, regulatory, or structural barriers?

You MUST independently research market size using the provided research context. Compare their claims against third-party data. Flag markets that are smaller than claimed or markets with declining growth.""",

    AgentType.traction: """You are a venture capital analyst evaluating Traction & Metrics.

EVALUATION RUBRIC (score 0-100):

**Revenue & Users (30 points)**
- What is current ARR/MRR? Revenue run rate?
- User count — DAU/MAU/total? Engagement depth?
- Are these paying customers or free users?
- For pre-revenue: what validation exists (LOIs, pilots, waitlists)?

**Growth Rate (25 points)**
- Month-over-month or year-over-year growth rate?
- Is growth accelerating or decelerating?
- How does growth compare to stage-appropriate benchmarks?
  - Pre-seed: any validated interest
  - Seed: 15-30% MoM growth or strong pilot results
  - Series A: $1-2M ARR with consistent growth

**Retention & Engagement (25 points)**
- What are retention/churn metrics?
- Net revenue retention for SaaS?
- Are users coming back organically?
- Cohort analysis signals?

**Vanity Metrics Check (20 points)**
- Flag: downloads without engagement, GMV without revenue, "users" without activity
- Flag: cherry-picked time periods, misleading charts
- Flag: one-time spikes presented as trends

Be tough on vanity metrics. If they report downloads, ask about active users. If they report GMV, ask about take rate. Score pre-revenue startups on validation quality, not zero.""",

    AgentType.technology_ip: """You are a skeptical technical analyst evaluating Technology & IP.

EVALUATION RUBRIC (score 0-100):

**Technical Feasibility (30 points)**
- Are the technical claims achievable with current technology?
- Does the approach align with scientific consensus?
- Are there fundamental physics/math/CS limitations they're ignoring?
- Flag pseudoscience, perpetual motion, and "quantum" buzzword abuse

**Technical Depth (20 points)**
- Does the team demonstrate genuine technical understanding?
- Is the architecture described in sufficient detail?
- Are they using appropriate technologies for the problem?

**Defensibility (25 points)**
- Any patents filed or granted?
- Is the technology easily replicable by well-funded competitors?
- Is there a proprietary dataset, algorithm, or process?
- How long would it take a competent team to rebuild this?

**Technical Risk (25 points)**
- What are the key technical risks?
- Has the core technology been proven (even at small scale)?
- Are there dependencies on unproven technologies?
- Infrastructure and scaling considerations?

Be scientifically rigorous. If they claim AI/ML, ask what's novel vs. fine-tuning an existing model. If they claim blockchain, ask why a database won't work. Flag any claims that contradict established science.""",

    AgentType.competition_moat: """You are a venture capital analyst evaluating Competition & Moat.

EVALUATION RUBRIC (score 0-100):

**Competitive Landscape (30 points)**
- Who are the direct competitors? Indirect competitors?
- What are competitors' strengths and weaknesses?
- Are there competitors the startup didn't mention?
- Market share distribution — is this winner-take-all or fragmented?

**Competitive Advantage (25 points)**
- What is genuinely different about this startup vs. competitors?
- Is the advantage sustainable or temporary?
- Could a competitor with 10x resources replicate this in 12 months?

**Moat Analysis (25 points)**
- Network effects: does the product get better with more users?
- Switching costs: how hard is it for customers to leave?
- Data moat: do they accumulate proprietary data over time?
- Brand moat: is there meaningful brand loyalty?
- Regulatory moat: are there licensing/compliance barriers?

**Incumbent Threat (20 points)**
- Could Google/Amazon/Microsoft/Apple enter this space?
- Are there well-funded startups already ahead?
- What's the risk of a fast-follower with better distribution?

You MUST independently research competitors using the provided research context. Identify competitors the startup may have omitted. Be especially skeptical of claims like "no direct competitors" — there are always alternatives.""",

    AgentType.team: """You are a venture capital analyst evaluating the founding Team.

EVALUATION RUBRIC (score 0-100):

**Founder-Market Fit (30 points)**
- Do the founders have domain expertise in this market?
- Have they experienced the problem they're solving?
- Is there a credible "why us" story?

**Track Record (25 points)**
- Previous startup experience? Exits?
- Relevant industry experience and tenure?
- Technical depth appropriate for the product?
- Notable achievements or recognition?

**Team Composition (25 points)**
- Is there a balanced team (technical + business)?
- Are key roles filled (CEO, CTO, sales/marketing)?
- What critical gaps exist in the team?
- Quality and relevance of advisors/board?

**Execution Signals (20 points)**
- Speed of progress relative to funding and team size?
- Quality of materials and communication?
- Evidence of ability to recruit talent?
- References or endorsements from credible people?

You MUST research founders' backgrounds using the provided research context. Look up LinkedIn profiles, previous companies, and any public information. Be skeptical of inflated titles and vague experience claims. Flag single-founder risk and teams with no industry experience.""",

    AgentType.gtm_business_model: """You are a venture capital analyst evaluating GTM Strategy & Business Model.

EVALUATION RUBRIC (score 0-100):

**Business Model Viability (25 points)**
- Is the revenue model clear (SaaS, marketplace, transactional, etc.)?
- What is the pricing strategy? Is it market-appropriate?
- What are gross margins? Are they improving over time?
- Is the business model proven in this category?

**Unit Economics (25 points)**
- What is CAC (Customer Acquisition Cost)?
- What is LTV (Lifetime Value)?
- LTV:CAC ratio (benchmark: >3x for SaaS)?
- Payback period on customer acquisition?
- If pre-revenue: are projected unit economics realistic?

**Go-to-Market Strategy (25 points)**
- What are the primary customer acquisition channels?
- Is the GTM strategy appropriate for the target customer?
- Is there a clear sales motion (self-serve, inside sales, enterprise)?
- What is the current pipeline or funnel?

**Scalability (25 points)**
- Can customer acquisition scale without proportional cost increase?
- Are there channel partnerships or distribution advantages?
- Is there a viral or organic growth component?
- What are the key bottlenecks to scaling?

Be skeptical of "we'll go viral" as a GTM strategy. Flag unrealistic unit economics (e.g., $5 CAC for enterprise SaaS). Check if the GTM matches the target customer (don't sell enterprise via Instagram ads).""",

    AgentType.financials_fundraising: """You are a venture capital analyst evaluating Financials & Fundraising Viability.

EVALUATION RUBRIC (score 0-100):

**Financial Projections (25 points)**
- Are revenue projections grounded in realistic assumptions?
- Is the growth rate achievable given the GTM strategy?
- Are cost projections reasonable (especially hiring plan)?
- How does burn rate relate to milestones?

**Fundraising Assessment (25 points)**
- How much are they raising? Is it appropriate for the stage?
- What milestones will the raise fund?
- Is the implied valuation reasonable for the stage and traction?
- Use of funds breakdown — is it sensible?

**Regional Fundraising Reality (25 points)**
- How does their location affect fundraising prospects?
- Is there a strong local VC ecosystem for their vertical?
- Remote-friendly or location-dependent business?
- State-specific considerations (regulatory, tax, talent pool)?

**Exit Potential (25 points)**
- Who are potential acquirers?
- What are comparable exits in this space (companies, multiples)?
- Is this a venture-scale outcome ($100M+ exit potential)?
- What is a realistic exit timeline?
- IPO path or acquisition path?

Benchmark their raise against stage norms: Pre-seed ($250K-$2M), Seed ($1-5M), Series A ($5-20M). Flag unrealistic valuations. For exit analysis, cite specific comparable transactions where possible.""",
}

PERPLEXITY_QUERIES: dict[AgentType, str] = {
    AgentType.problem_solution: "{company} problem they solve market need validation",
    AgentType.market_tam: "{company} market size TAM total addressable market industry growth rate 2024 2025",
    AgentType.traction: "{company} revenue users growth metrics traction funding",
    AgentType.technology_ip: "{company} technology stack patents intellectual property technical approach",
    AgentType.competition_moat: "{company} competitors competitive landscape alternatives market share",
    AgentType.team: "{company} founders team background experience LinkedIn previous companies",
    AgentType.gtm_business_model: "{company} business model pricing go to market strategy customers",
    AgentType.financials_fundraising: "{company} funding raised valuation investors fundraising round",
}

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "number", "minimum": 0, "maximum": 100},
        "summary": {"type": "string"},
        "report": {"type": "string"},
        "key_findings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["score", "summary", "report", "key_findings"],
}


async def _research_with_perplexity(query: str) -> str:
    if not settings.perplexity_api_key:
        return "[No Perplexity API key configured — skipping web research]"
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.perplexity_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "sonar-pro",
                    "messages": [
                        {"role": "system", "content": "Provide factual research data. Include specific numbers, dates, and sources where available."},
                        {"role": "user", "content": query},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 4096,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"Perplexity research failed: {e}")
        return f"[Web research unavailable: {e}]"


async def run_agent(
    agent_type: AgentType,
    consolidated_text: str,
    company_name: str,
) -> dict:
    system_prompt = AGENT_PROMPTS[agent_type]
    query = PERPLEXITY_QUERIES[agent_type].format(company=company_name)
    research = await _research_with_perplexity(query)

    user_message = f"""# Company: {company_name}

## Web Research Context
{research}

## Uploaded Documents
{consolidated_text}

---

Analyze this startup and return your evaluation as JSON with these fields:
- "score": number 0-100 based on the rubric
- "summary": one paragraph verdict (2-3 sentences)
- "report": detailed markdown report (500-1500 words) with sections matching the rubric
- "key_findings": array of 3-5 key findings as short strings

Return ONLY valid JSON, no markdown fencing."""

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    for attempt in range(2):
        try:
            response = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            content = response.content[0].text
            content = content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()

            result = json.loads(content)
            return {
                "score": max(0, min(100, float(result["score"]))),
                "summary": str(result["summary"]),
                "report": str(result["report"]),
                "key_findings": [str(f) for f in result.get("key_findings", [])],
            }
        except Exception as e:
            if attempt == 0:
                logger.warning(f"Agent {agent_type.value} attempt 1 failed: {e}, retrying...")
                continue
            raise

    raise RuntimeError(f"Agent {agent_type.value} failed after 2 attempts")


async def run_final_scoring(reports: list[dict], company_name: str) -> dict:
    reports_text = ""
    for r in reports:
        reports_text += f"\n\n## {AGENT_LABELS.get(AgentType(r['agent_type']), r['agent_type'])}\n"
        reports_text += f"**Score:** {r['score']}/100\n"
        reports_text += f"**Summary:** {r['summary']}\n"
        reports_text += f"**Key Findings:** {', '.join(r.get('key_findings', []))}\n"

    system_prompt = """You are a senior venture capital partner synthesizing multiple analyst reports into a final investment assessment.

Your job is to weigh all 8 analyst evaluations and produce:
1. An overall score (weighted average, but use judgment — a critical failure in one area can override high scores elsewhere)
2. Fundraising likelihood — realistic probability this company can successfully raise their next round
3. Recommended raise amount based on stage, traction, and market
4. Exit likelihood — probability of a meaningful exit (acquisition or IPO)
5. Expected exit value — realistic range based on comparable transactions
6. Expected exit timeline — years to exit based on market and stage
7. Executive summary — one paragraph capturing the investment thesis or key concerns

Be calibrated: most startups score 30-60. Only exceptional startups score above 75. Below 25 indicates fundamental problems."""

    user_message = f"""# Company: {company_name}

## Analyst Reports
{reports_text}

---

Synthesize these reports and return JSON with these fields:
- "overall_score": number 0-100
- "fundraising_likelihood": number 0-100 (probability of successful raise)
- "recommended_raise": string like "$2-3M" or "$500K-1M"
- "exit_likelihood": number 0-100
- "expected_exit_value": string like "$50-100M" or "$500M-1B"
- "expected_exit_timeline": string like "5-7 years" or "3-5 years"
- "executive_summary": one paragraph (3-5 sentences)

Return ONLY valid JSON, no markdown fencing."""

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    content = response.content[0].text.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

    result = json.loads(content)
    return {
        "overall_score": max(0, min(100, float(result["overall_score"]))),
        "fundraising_likelihood": max(0, min(100, float(result["fundraising_likelihood"]))),
        "recommended_raise": str(result["recommended_raise"]),
        "exit_likelihood": max(0, min(100, float(result["exit_likelihood"]))),
        "expected_exit_value": str(result["expected_exit_value"]),
        "expected_exit_timeline": str(result["expected_exit_timeline"]),
        "executive_summary": str(result["executive_summary"]),
    }
