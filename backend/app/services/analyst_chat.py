"""Perplexity streaming chat service with chart extraction.

Streams Perplexity sonar-pro responses and extracts :::chart::: blocks
from the completed response.
"""

import json
import logging
import re
from collections.abc import AsyncGenerator

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

CHART_PATTERN = re.compile(r":::chart\s*\n?(.*?)\n?:::", re.DOTALL)

REQUIRED_CHART_KEYS = {"type", "data"}


def extract_charts(text: str) -> tuple[str, list[dict]]:
    """Extract :::chart JSON::: blocks from text.

    Returns (cleaned_text, list_of_chart_configs).
    Invalid chart JSON is silently skipped.
    """
    charts = []
    for match in CHART_PATTERN.finditer(text):
        raw = match.group(1).strip()
        try:
            chart = json.loads(raw)
            if REQUIRED_CHART_KEYS.issubset(chart.keys()):
                charts.append(chart)
            else:
                logger.warning("Chart missing required keys: %s", chart.keys())
        except json.JSONDecodeError as e:
            logger.warning("Invalid chart JSON: %s", e)

    cleaned = CHART_PATTERN.sub("", text).strip()
    # Remove double blank lines left by chart removal
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned, charts


async def stream_perplexity(
    messages: list[dict],
    system_prompt: str,
) -> AsyncGenerator[dict, None]:
    """Stream a Perplexity sonar-pro response.

    Yields dicts with one of:
      {"type": "text", "chunk": str}
      {"type": "citations", "citations": list}
      {"type": "done", "full_text": str}
      {"type": "error", "message": str}
    """
    if not settings.perplexity_api_key:
        yield {"type": "error", "message": "Perplexity API key not configured"}
        return

    api_messages = [{"role": "system", "content": system_prompt}] + messages

    full_text = ""
    citations = []

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                "https://api.perplexity.ai/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.perplexity_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "sonar-pro",
                    "temperature": 0.3,
                    "max_tokens": 4096,
                    "stream": True,
                    "messages": api_messages,
                },
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    yield {"type": "error", "message": f"Perplexity API error: {response.status_code}"}
                    return

                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data: "):
                        continue

                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break

                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    # Extract text delta
                    choices = data.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            full_text += content
                            yield {"type": "text", "chunk": content}

                    # Extract citations from response metadata
                    if "citations" in data:
                        citations = data["citations"]

    except httpx.ReadTimeout:
        yield {"type": "error", "message": "Perplexity response timed out"}
        return
    except Exception as e:
        logger.error("Perplexity streaming error: %s", e)
        yield {"type": "error", "message": f"Streaming error: {str(e)}"}
        return

    # Post-processing: extract charts from full text
    cleaned_text, charts = extract_charts(full_text)

    if citations:
        formatted = []
        for c in citations:
            if isinstance(c, str):
                formatted.append({"url": c, "title": c})
            elif isinstance(c, dict):
                formatted.append({"url": c.get("url", ""), "title": c.get("title", c.get("url", ""))})
        yield {"type": "citations", "citations": formatted}

    yield {
        "type": "done",
        "full_text": cleaned_text,
        "charts": charts,
        "raw_text": full_text,
    }
