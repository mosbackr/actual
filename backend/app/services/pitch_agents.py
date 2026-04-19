import json
import logging
import uuid

import anthropic
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)

SONNET_MODEL = "claude-sonnet-4-6-20250514"
OPUS_MODEL = "claude-opus-4-6-20250514"


def _build_transcript_text(labeled: dict) -> str:
    """Convert labeled transcript JSON into readable text for the AI prompt."""
    lines = []
    for seg in labeled.get("segments", []):
        name = seg.get("speaker_name", "Unknown")
        role = seg.get("speaker_role", "other")
        timestamp = _format_time(seg.get("start", 0))
        text = seg.get("text", "")
        lines.append(f"[{timestamp}] {name} ({role}): {text}")
    return "\n".join(lines)


def _format_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


async def _perplexity_search(query: str) -> str:
    """Reuse the existing Perplexity search pattern."""
    if not settings.perplexity_api_key:
        return "Perplexity API key not configured — web search unavailable."
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
                        {
                            "role": "system",
                            "content": (
                                "Provide concise, factual research data. Include specific "
                                "numbers, dates, and sources where available. Keep responses focused and "
                                "under 500 words — prioritize hard data over commentary."
                            ),
                        },
                        {"role": "user", "content": query},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 2048,
                },
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            if len(content) > 3000:
                content = content[:3000] + "\n\n[Response truncated for brevity]"
            return content
    except Exception as e:
        logger.warning("Perplexity search failed: %s", e)
        return f"Search failed: {e}"


# ── Phase 1: Claim Extraction ─────────────────────────────────────────


async def run_claim_extraction(transcript_labeled: dict) -> dict:
    """Extract factual claims from founders and advice/assertions from investors."""
    transcript_text = _build_transcript_text(transcript_labeled)

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model=SONNET_MODEL,
        max_tokens=8192,
        system=(
            "You are an expert pitch analyst. Extract every factual claim made by founders "
            "(revenue numbers, growth rates, market size, user counts, competitive advantages, "
            "timelines) and every piece of advice or assertion made by investors (market opinions, "
            "valuation benchmarks, strategic suggestions, comparisons to other companies).\n\n"
            "Return a JSON object with two arrays:\n"
            "- \"founder_claims\": each with {\"speaker\", \"timestamp\", \"quote\", \"category\", \"claim_summary\"}\n"
            "- \"investor_claims\": each with {\"speaker\", \"timestamp\", \"quote\", \"category\", \"claim_summary\"}\n\n"
            "Categories for founders: revenue, growth, market_size, users, competitive, timeline, team, technology, unit_economics, other\n"
            "Categories for investors: market_opinion, valuation, strategy, comparison, risk, other\n\n"
            "Be thorough — extract every verifiable claim. Return valid JSON only."
        ),
        messages=[{"role": "user", "content": f"Transcript:\n\n{transcript_text}"}],
    )

    text = response.content[0].text
    # Parse JSON from response (handle markdown code blocks)
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse claim extraction JSON, returning raw text")
        return {"founder_claims": [], "investor_claims": [], "raw_text": text}


# ── Phase 2: Fact-Checking ────────────────────────────────────────────


async def run_fact_check(claims: dict, claim_type: str) -> dict:
    """
    Fact-check a set of claims using Perplexity search.
    claim_type: "founder" or "investor"
    """
    key = "founder_claims" if claim_type == "founder" else "investor_claims"
    claim_list = claims.get(key, [])

    if not claim_list:
        return {"claims": [], "summary": f"No {claim_type} claims to verify."}

    # Search for verification data on each claim (batch similar ones)
    verification_data = {}
    for i, claim in enumerate(claim_list):
        summary = claim.get("claim_summary", claim.get("quote", ""))
        if summary:
            search_result = await _perplexity_search(
                f"Verify: {summary}"
            )
            verification_data[i] = search_result

    # Now have Claude evaluate each claim against the search results
    claims_text = json.dumps(claim_list, indent=2)
    verification_text = json.dumps(verification_data, indent=2)

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model=SONNET_MODEL,
        max_tokens=8192,
        system=(
            f"You are a fact-checking analyst. Evaluate each {claim_type} claim against the "
            "verification data provided from web searches.\n\n"
            "For each claim, provide:\n"
            "- \"verdict\": one of \"verified\", \"disputed\", \"unverifiable\"\n"
            "- \"confidence\": 0-100\n"
            "- \"explanation\": why you reached this verdict\n"
            "- \"sources\": relevant sources from the verification data\n"
            "- \"original_claim\": the original claim object\n\n"
            "Return a JSON object with:\n"
            "- \"checked_claims\": array of evaluated claims\n"
            "- \"summary\": overall assessment paragraph\n"
            "- \"verified_count\", \"disputed_count\", \"unverifiable_count\": integers\n\n"
            "Return valid JSON only."
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    f"Claims to verify:\n{claims_text}\n\n"
                    f"Verification data from web searches:\n{verification_text}"
                ),
            }
        ],
    )

    text = response.content[0].text
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"checked_claims": [], "summary": text, "raw_text": text}


# ── Phase 3: Conversation Analysis ───────────────────────────────────


async def run_conversation_analysis(transcript_labeled: dict, fact_check_results: dict) -> dict:
    """Analyze presentation quality, meeting dynamics, and strategic read."""
    transcript_text = _build_transcript_text(transcript_labeled)

    fact_check_summary = ""
    for key in ["founder_fact_check", "investor_fact_check"]:
        fc = fact_check_results.get(key, {})
        if isinstance(fc, dict) and fc.get("summary"):
            fact_check_summary += f"\n{key}: {fc['summary']}\n"

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model=OPUS_MODEL,
        max_tokens=8192,
        system=(
            "You are a senior venture capital advisor analyzing a pitch meeting. "
            "Evaluate the conversation across three dimensions:\n\n"
            "1. **Presentation Quality**: pacing, filler words, confidence level, clarity of explanations, "
            "how well founders handled tough questions, storytelling effectiveness\n\n"
            "2. **Meeting Dynamics**: who dominated the conversation (with percentage estimates), "
            "investor engagement level, tension points, moments where founders got defensive, "
            "rapport building, turn-taking patterns\n\n"
            "3. **Strategic Read**: investor interest signals (positive and negative), concerns "
            "that weren't voiced but were implied by questions, how the power dynamic shifted "
            "during the session, likelihood of follow-up\n\n"
            "For each dimension, cite specific moments from the transcript with timestamps.\n\n"
            "Return a JSON object with:\n"
            "- \"presentation_quality\": {\"score\": 0-100, \"assessment\": string, \"highlights\": [{\"timestamp\", \"observation\"}], \"improvements\": [string]}\n"
            "- \"meeting_dynamics\": {\"score\": 0-100, \"assessment\": string, \"speaker_balance\": {name: percentage}, \"key_moments\": [{\"timestamp\", \"observation\"}], \"tension_points\": [{\"timestamp\", \"description\"}]}\n"
            "- \"strategic_read\": {\"score\": 0-100, \"assessment\": string, \"interest_signals\": [{\"timestamp\", \"signal\", \"polarity\"}], \"unvoiced_concerns\": [string], \"follow_up_likelihood\": string}\n"
            "- \"overall_environment_score\": 0-100\n"
            "- \"environment_summary\": string\n\n"
            "Return valid JSON only."
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    f"Pitch meeting transcript:\n\n{transcript_text}\n\n"
                    f"Fact-check context:\n{fact_check_summary}"
                ),
            }
        ],
    )

    text = response.content[0].text
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw_text": text}


# ── Phase 4: Scoring & Recommendations ───────────────────────────────


async def run_scoring(
    transcript_labeled: dict,
    claims: dict,
    fact_check_results: dict,
    conversation_analysis: dict,
) -> dict:
    """Generate final scores and prioritized recommendations."""
    transcript_text = _build_transcript_text(transcript_labeled)

    # Build context from prior phases
    prior_context = json.dumps({
        "claims_extracted": {
            "founder_count": len(claims.get("founder_claims", [])),
            "investor_count": len(claims.get("investor_claims", [])),
        },
        "fact_check": {
            k: {
                "verified": v.get("verified_count", 0),
                "disputed": v.get("disputed_count", 0),
                "unverifiable": v.get("unverifiable_count", 0),
                "summary": v.get("summary", ""),
            }
            for k, v in fact_check_results.items()
            if isinstance(v, dict)
        },
        "conversation_analysis": {
            k: v.get("score", 0) if isinstance(v, dict) else v
            for k, v in conversation_analysis.items()
            if k in ("presentation_quality", "meeting_dynamics", "strategic_read", "overall_environment_score")
        },
    }, indent=2)

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model=OPUS_MODEL,
        max_tokens=8192,
        system=(
            "You are a senior pitch coach and venture analyst. Based on the full transcript "
            "and all prior analysis phases, generate final scores and actionable recommendations.\n\n"
            "Score each dimension 0-100:\n"
            "- pitch_clarity: How clear and compelling was the pitch narrative?\n"
            "- financial_rigor: How solid were the financial claims and projections?\n"
            "- q_and_a_handling: How well did founders handle investor questions?\n"
            "- investor_engagement: How engaged and interested were the investors?\n"
            "- fact_accuracy: What percentage of verifiable claims checked out?\n"
            "- overall: Weighted overall pitch effectiveness\n\n"
            "Then provide 5-10 prioritized recommendations, each tied to a specific transcript moment.\n\n"
            "Return a JSON object with:\n"
            "- \"scores\": {\"pitch_clarity\": int, \"financial_rigor\": int, \"q_and_a_handling\": int, \"investor_engagement\": int, \"fact_accuracy\": int, \"overall\": int}\n"
            "- \"recommendations\": [{\"priority\": 1-10, \"title\": string, \"description\": string, \"transcript_reference\": string, \"impact\": \"high\"|\"medium\"|\"low\"}]\n"
            "- \"executive_summary\": string (2-3 paragraph overall assessment)\n\n"
            "Return valid JSON only."
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    f"Transcript:\n\n{transcript_text}\n\n"
                    f"Analysis context:\n{prior_context}"
                ),
            }
        ],
    )

    text = response.content[0].text
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw_text": text}
