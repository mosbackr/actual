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
# Also match ```json blocks or bare JSON blocks that look like charts
JSON_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*\n(\{[^`]*?\})\s*\n```", re.DOTALL)
# Bare JSON objects on their own lines that look like chart configs
BARE_JSON_PATTERN = re.compile(
    r'(?:^|\n)\s*(\{"type"\s*:\s*"(?:bar|line|pie|scatter|area)"[^}]*\{[^}]*\}[^}]*\})',
    re.DOTALL,
)

REQUIRED_CHART_KEYS = {"type", "data"}
CHART_TYPES = {"bar", "line", "pie", "scatter", "area"}


def _try_parse_chart(raw: str) -> dict | None:
    """Try to parse a string as a chart config JSON."""
    try:
        chart = json.loads(raw)
        if isinstance(chart, dict) and REQUIRED_CHART_KEYS.issubset(chart.keys()):
            if chart.get("type") in CHART_TYPES:
                return chart
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def extract_charts(text: str) -> tuple[str, list[dict]]:
    """Extract chart JSON blocks from text.

    Supports :::chart JSON:::, ```json blocks, and bare JSON chart objects.
    Returns (cleaned_text, list_of_chart_configs).
    """
    charts = []
    cleaned = text

    # 1. Try :::chart::: format first
    for match in CHART_PATTERN.finditer(text):
        chart = _try_parse_chart(match.group(1).strip())
        if chart:
            charts.append(chart)
    if charts:
        cleaned = CHART_PATTERN.sub("", cleaned).strip()
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned, charts

    # 2. Try ```json code blocks
    for match in JSON_BLOCK_PATTERN.finditer(text):
        chart = _try_parse_chart(match.group(1).strip())
        if chart:
            charts.append(chart)
    if charts:
        cleaned = JSON_BLOCK_PATTERN.sub("", cleaned).strip()
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned, charts

    # 3. Try finding bare JSON that looks like a chart (has "type": "bar|line|...")
    # Find all JSON-like blocks
    brace_depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == '{' and start is None:
            start = i
            brace_depth = 1
        elif ch == '{' and start is not None:
            brace_depth += 1
        elif ch == '}' and start is not None:
            brace_depth -= 1
            if brace_depth == 0:
                candidate = text[start:i+1]
                chart = _try_parse_chart(candidate)
                if chart:
                    charts.append(chart)
                    cleaned = cleaned.replace(candidate, "", 1)
                start = None

    if charts:
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

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
