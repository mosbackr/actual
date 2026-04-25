import json
import logging

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

SONNET_MODEL = "claude-sonnet-4-6"


async def generate_investor_faq(analysis_data: dict, source_type: str) -> dict:
    """Generate investor FAQ from analysis data.

    Args:
        analysis_data: Dict with all scores, summaries, key findings, etc.
        source_type: "pitch_analysis" or "pitch_intelligence"

    Returns:
        Dict with "generated_at" and "questions" list.
    """
    from datetime import datetime, timezone

    context_text = _build_context(analysis_data, source_type)

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model=SONNET_MODEL,
        max_tokens=8192,
        system=(
            "You are a senior venture capital advisor helping founders prepare for investor meetings. "
            "Based on the pitch analysis data provided, generate 15-25 likely investor questions and "
            "coached answers.\n\n"
            "For each question:\n"
            "1. Identify weaknesses, gaps, red flags, and areas where scores are low\n"
            "2. Generate tough but realistic questions an investor would ask about those areas\n"
            "3. Provide a coached answer that acknowledges the concern honestly while presenting "
            "the strongest possible case\n"
            "4. Also include standard investor questions that are always asked (team background, "
            "use of funds, competitive differentiation, unit economics, etc.)\n\n"
            "Categorize each Q&A into exactly one of these categories: "
            "market, traction, financials, team, technology, competition, business_model, risk\n\n"
            "Assign a priority to each question:\n"
            "- \"high\": Very likely to be asked — addresses obvious weak spots or standard investor concerns\n"
            "- \"medium\": Likely to come up in a thorough meeting\n"
            "- \"low\": Possible follow-up or deep-dive question\n\n"
            "Return a JSON array of objects, each with:\n"
            "- \"category\": one of the 8 categories above\n"
            "- \"question\": the investor's question\n"
            "- \"answer\": the coached answer (2-4 sentences)\n"
            "- \"priority\": \"high\", \"medium\", or \"low\"\n\n"
            "Order by priority (all high first, then medium, then low). "
            "Return ONLY the JSON array, no other text."
        ),
        messages=[{"role": "user", "content": context_text}],
    )

    text = response.content[0].text
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        questions = json.loads(text)
    except json.JSONDecodeError:
        logger.error("Failed to parse FAQ JSON: %s", text[:500])
        questions = []

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "questions": questions,
    }


def _build_context(data: dict, source_type: str) -> str:
    """Build the context string for the Claude prompt from analysis data."""
    parts = []

    company = data.get("company_name") or data.get("title") or "Unknown Company"
    parts.append(f"Company/Pitch: {company}")

    if source_type == "pitch_analysis":
        if data.get("overall_score") is not None:
            parts.append(f"Overall Score: {data['overall_score']}/100")
        if data.get("fundraising_likelihood") is not None:
            parts.append(f"Fundraising Likelihood: {data['fundraising_likelihood']}%")
        if data.get("recommended_raise"):
            parts.append(f"Recommended Raise: {data['recommended_raise']}")
        if data.get("estimated_valuation"):
            parts.append(f"Estimated Valuation: {data['estimated_valuation']}")
        if data.get("valuation_justification"):
            parts.append(f"Valuation Justification: {data['valuation_justification']}")
        if data.get("executive_summary"):
            parts.append(f"Executive Summary: {data['executive_summary']}")
        if data.get("exit_likelihood") is not None:
            parts.append(f"Exit Likelihood: {data['exit_likelihood']}%")
        if data.get("expected_exit_value"):
            parts.append(f"Expected Exit Value: {data['expected_exit_value']}")

        ter = data.get("technical_expert_review")
        if ter and isinstance(ter, dict):
            parts.append(f"Technical Feasibility: {ter.get('technical_feasibility', 'N/A')}")
            parts.append(f"TRL Level: {ter.get('trl_level', 'N/A')}")
            if ter.get("red_flags"):
                parts.append(f"Technical Red Flags: {', '.join(ter['red_flags'])}")
            if ter.get("scientific_consensus"):
                parts.append(f"Scientific Consensus: {ter['scientific_consensus']}")

        reports = data.get("reports") or []
        for r in reports:
            agent = r.get("agent_type", "unknown")
            score = r.get("score")
            summary = r.get("summary", "")
            key_findings = r.get("key_findings") or []
            parts.append(f"\n--- {agent} (Score: {score}/100) ---")
            if summary:
                parts.append(f"Summary: {summary}")
            if key_findings:
                parts.append(f"Key Findings: {'; '.join(str(f) for f in key_findings)}")

    elif source_type == "pitch_intelligence":
        scores = data.get("scores") or {}
        for dim, val in scores.items():
            parts.append(f"Score - {dim}: {val}/100")

        results = data.get("results") or []
        for r in results:
            phase = r.get("phase", "unknown")
            result_data = r.get("result")
            if not result_data:
                continue

            if phase == "scoring":
                if result_data.get("executive_summary"):
                    parts.append(f"Executive Summary: {result_data['executive_summary']}")
                recs = result_data.get("recommendations") or []
                if recs:
                    rec_texts = [f"- {rec.get('title', '')}: {rec.get('description', '')}" for rec in recs[:10]]
                    parts.append("Recommendations:\n" + "\n".join(rec_texts))
                va = result_data.get("valuation_assessment")
                if va:
                    parts.append(f"Estimated Valuation: {va.get('estimated_valuation', 'N/A')}")
                    parts.append(f"Valuation Justification: {va.get('justification', '')}")
                ter = result_data.get("technical_expert_review")
                if ter:
                    parts.append(f"Technical Feasibility: {ter.get('technical_feasibility', 'N/A')}")
                    if ter.get("red_flags"):
                        parts.append(f"Technical Red Flags: {', '.join(ter['red_flags'])}")

            elif phase == "claim_extraction":
                founder_claims = result_data.get("founder_claims") or []
                if founder_claims:
                    claims_text = [c.get("claim_summary", c.get("quote", "")) for c in founder_claims[:15]]
                    parts.append(f"Founder Claims: {'; '.join(claims_text)}")

            elif phase in ("fact_check_founders", "fact_check_investors"):
                summary = result_data.get("summary", "")
                disputed = result_data.get("disputed_count", 0)
                if summary:
                    parts.append(f"Fact Check ({phase}): {summary}")
                if disputed:
                    parts.append(f"Disputed claims: {disputed}")

            elif phase == "conversation_analysis":
                for section in ("presentation_quality", "meeting_dynamics", "strategic_read"):
                    section_data = result_data.get(section)
                    if section_data and isinstance(section_data, dict):
                        parts.append(f"{section} (Score: {section_data.get('score', 'N/A')}): {section_data.get('assessment', '')[:300]}")

    return "\n".join(parts)
