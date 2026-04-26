import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio


# Override the autouse setup_db fixture from conftest so these pure unit tests
# don't require a running PostgreSQL instance.
@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    yield None


@pytest.mark.asyncio
async def test_generate_email_html_calls_anthropic():
    """Verify generate_email_html calls Claude with the brand system prompt
    containing brand colours and required placeholders."""

    fake_response = MagicMock()
    fake_response.content = [MagicMock(text="<html>generated</html>")]

    with patch(
        "app.services.marketing_email.client"
    ) as mock_client:
        mock_client.messages.create = AsyncMock(return_value=fake_response)

        from app.services.marketing_email import (
            BRAND_SYSTEM_PROMPT,
            generate_email_html,
        )

        result = await generate_email_html("Write an investor outreach email")

        mock_client.messages.create.assert_awaited_once()
        call_kwargs = mock_client.messages.create.call_args

        # System prompt should be the brand prompt
        assert call_kwargs.kwargs["system"] == BRAND_SYSTEM_PROMPT

        # Brand colours present in the system prompt
        assert "#F28C28" in BRAND_SYSTEM_PROMPT
        assert "#FAFAF8" in BRAND_SYSTEM_PROMPT
        assert "#1A1A1A" in BRAND_SYSTEM_PROMPT
        assert "#E8E6E3" in BRAND_SYSTEM_PROMPT

        # Placeholders present in the system prompt
        assert "{{score}}" in BRAND_SYSTEM_PROMPT
        assert "{{cta_url}}" in BRAND_SYSTEM_PROMPT

        # Model should be claude-sonnet-4-6
        assert call_kwargs.kwargs["model"] == "claude-sonnet-4-6"

        # The user prompt is forwarded
        user_msg = call_kwargs.kwargs["messages"][0]["content"]
        assert user_msg == "Write an investor outreach email"

        # Returns the generated HTML
        assert result == "<html>generated</html>"


def test_render_for_recipient_replaces_placeholders():
    """Verify render_for_recipient replaces {{score}} and {{cta_url}} correctly."""
    from app.services.marketing_email import render_for_recipient

    template = (
        "<html><body>"
        "<p>Your score: {{score}}</p>"
        '<a href="{{cta_url}}">View</a>'
        "</body></html>"
    )

    class FakeRanking:
        overall_score = 87.6

    investor_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
    frontend_url = "https://app.deepthesis.org"

    result = render_for_recipient(template, FakeRanking(), investor_id, frontend_url)

    # Score should be rounded to integer
    assert "88" in result
    assert "{{score}}" not in result

    # CTA URL should point to the score page
    expected_url = f"https://app.deepthesis.org/score/{investor_id}"
    assert expected_url in result
    assert "{{cta_url}}" not in result
