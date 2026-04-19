"""Claude-powered feedback collection agent.

Conducts a short feedback conversation (2-4 follow-up questions),
then summarizes with structured tags and recommendations.
"""

import json
import logging
from collections.abc import AsyncGenerator

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

FEEDBACK_SYSTEM_PROMPT = """\
You are DeepThesis's feedback collection assistant. Your job is to help users report bugs, \
request features, or share suggestions about the DeepThesis platform.

Guidelines:
- Start by understanding what the user wants to share
- Ask 2-4 targeted follow-up questions, ONE at a time, to clarify:
  - For bugs: steps to reproduce, expected vs actual behavior, severity
  - For features: desired behavior, use case, priority
  - For UX issues: what felt wrong, what they expected
- Keep responses short and conversational (1-3 sentences)
- Be appreciative — thank them for their feedback
- After gathering enough context (2-4 exchanges), respond with a brief confirmation \
like "Thanks, I've captured this feedback!" — do NOT ask more questions after that
- Never make promises about timelines or implementation
- Do not discuss topics unrelated to DeepThesis platform feedback
"""

SUMMARIZE_SYSTEM_PROMPT = """\
Analyze this feedback conversation and produce a structured summary.

Return a JSON object with:
- "summary": 2-3 sentence description of the feedback
- "category": exactly one of: "bug", "feature_request", "ux_issue", "performance", "general"
- "severity": exactly one of: "critical", "high", "medium", "low"
- "area": the site section discussed (e.g. "pitch-intelligence", "analyst", "startups", \
"billing", "insights", "navigation", "auth", "general")
- "recommendations": array of 2-5 objects, each with:
  - "title": short action title
  - "description": what to do
  - "priority": 1 (highest) to 5 (lowest)

Return valid JSON only.
"""


async def stream_feedback_response(
    transcript: list[dict],
) -> AsyncGenerator[dict, None]:
    """Stream a Claude response for the feedback conversation.

    Args:
        transcript: list of {"role": "user"|"assistant", "content": str}

    Yields:
        {"type": "text", "chunk": str} for streamed text
        {"type": "done", "full_text": str} when complete
    """
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    messages = [{"role": m["role"], "content": m["content"]} for m in transcript]

    full_text = ""
    try:
        async with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=FEEDBACK_SYSTEM_PROMPT,
            messages=messages,
        ) as stream:
            async for event in stream:
                if event.type == "content_block_delta" and hasattr(event.delta, "text"):
                    full_text += event.delta.text
                    yield {"type": "text", "chunk": event.delta.text}
    except Exception as e:
        logger.error("Feedback agent streaming error: %s", e)
        yield {"type": "error", "message": "An error occurred processing your feedback."}
        return

    yield {"type": "done", "full_text": full_text}


async def summarize_feedback(transcript: list[dict]) -> dict:
    """Call Claude to summarize a completed feedback conversation.

    Returns dict with summary, category, severity, area, recommendations.
    """
    conversation_text = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in transcript
    )

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=SUMMARIZE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Feedback conversation:\n\n{conversation_text}"}],
    )

    text = response.content[0].text
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse feedback summary JSON")
        return {
            "summary": text[:500],
            "category": "general",
            "severity": "medium",
            "area": "general",
            "recommendations": [],
        }
