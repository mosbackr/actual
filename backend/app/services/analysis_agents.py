import json
import logging
import uuid
from datetime import datetime

import anthropic
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.pitch_analysis import AgentType
from app.services.agent_tools import AGENT_TOOLS, execute_tool

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

You have access to Perplexity web search (which can query Crunchbase, PitchBook, and the open web) and the DeepThesis startup database. Use your tools aggressively to validate claims in the pitch deck, find comparable companies, and research market conditions.

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

You have access to Perplexity web search (which can query Crunchbase, PitchBook, and the open web) and the DeepThesis startup database. Use your tools to independently research and verify market size claims.

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

You MUST independently research market size using your Perplexity search tool. Compare their claims against third-party data. Flag markets that are smaller than claimed or markets with declining growth.""",

    AgentType.traction: """You are a venture capital analyst evaluating Traction & Metrics.

You have access to Perplexity web search (which can query Crunchbase, PitchBook, and the open web) and the DeepThesis startup database. Use your tools to verify claims and find comparable benchmarks.

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

You have access to Perplexity web search (which can query Crunchbase, PitchBook, and the open web) and the DeepThesis startup database. Use your tools to verify technical claims, check patents, and assess feasibility.

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

You have access to Perplexity web search (which can query Crunchbase, PitchBook, and the open web) and the DeepThesis startup database. Use your tools aggressively to identify ALL competitors — especially ones the startup may have omitted.

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

You MUST independently research competitors using your Perplexity search tool. Identify competitors the startup may have omitted. Be especially skeptical of claims like "no direct competitors" — there are always alternatives.""",

    AgentType.team: """You are a venture capital analyst evaluating the founding Team.

You have access to Perplexity web search (which can query Crunchbase, PitchBook, and the open web) and the DeepThesis startup database. Use your tools to research founders' backgrounds, previous companies, and track records.

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

You MUST research founders' backgrounds using your Perplexity search tool. Look up LinkedIn profiles, previous companies, and any public information. Be skeptical of inflated titles and vague experience claims. Flag single-founder risk and teams with no industry experience.""",

    AgentType.gtm_business_model: """You are a venture capital analyst evaluating GTM Strategy & Business Model.

You have access to Perplexity web search (which can query Crunchbase, PitchBook, and the open web) and the DeepThesis startup database. Use your tools to verify pricing, benchmark unit economics, and assess GTM viability.

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

You have access to Perplexity web search (which can query Crunchbase, PitchBook, and the open web) and the DeepThesis startup database. Use your tools to benchmark fundraising, check comparable deals, and verify financial claims.

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


async def run_agent(
    agent_type: AgentType,
    consolidated_text: str,
    company_name: str,
    analysis_id: uuid.UUID,
    db: AsyncSession,
) -> dict:
    """Run a single agent in a tool-use loop until it produces a final report."""
    system_prompt = AGENT_PROMPTS[agent_type]

    user_message = f"""# Company: {company_name}

## Uploaded Documents
{consolidated_text}

---

First, use your tools to research this company — validate their claims, find competitors, check market data, look up founders, etc. Be thorough.

Then, once you have enough information, provide your final evaluation as JSON with these fields:
- "score": number 0-100 based on the rubric
- "summary": one paragraph verdict (2-3 sentences)
- "report": detailed markdown report (500-1500 words) with sections matching the rubric
- "key_findings": array of 3-5 key findings as short strings

Return ONLY valid JSON when you're ready to submit your final evaluation, no markdown fencing."""

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    messages = [{"role": "user", "content": user_message}]

    for attempt in range(2):
        try:
            # Tool-use conversation loop
            while True:
                response = await client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=4096,
                    system=system_prompt,
                    messages=messages,
                    tools=AGENT_TOOLS,
                )

                # Check if Claude wants to use tools
                if response.stop_reason == "tool_use":
                    # Process all tool calls in this response
                    assistant_content = response.content
                    tool_results = []

                    for block in assistant_content:
                        if block.type == "tool_use":
                            result_text = await execute_tool(
                                tool_name=block.name,
                                tool_input=block.input,
                                analysis_id=analysis_id,
                                agent_type=agent_type.value,
                                db=db,
                            )
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result_text,
                            })

                    # Add assistant message and tool results to conversation
                    messages.append({"role": "assistant", "content": assistant_content})
                    messages.append({"role": "user", "content": tool_results})
                    continue

                # Claude is done — extract the final text response
                text_content = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        text_content += block.text

                text_content = text_content.strip()
                if text_content.startswith("```"):
                    text_content = text_content.split("\n", 1)[1]
                    if text_content.endswith("```"):
                        text_content = text_content[:-3]
                    text_content = text_content.strip()

                result = json.loads(text_content)
                return {
                    "score": max(0, min(100, float(result["score"]))),
                    "summary": str(result["summary"]),
                    "report": str(result["report"]),
                    "key_findings": [str(f) for f in result.get("key_findings", [])],
                }

        except Exception as e:
            if attempt == 0:
                logger.warning("Agent %s attempt 1 failed: %s, retrying...", agent_type.value, e)
                messages = [{"role": "user", "content": user_message}]
                continue
            raise

    raise RuntimeError(f"Agent {agent_type.value} failed after 2 attempts")


async def run_final_scoring(reports: list[dict], company_name: str) -> dict:
    """Synthesize all agent reports into a final score. No tools needed."""
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
