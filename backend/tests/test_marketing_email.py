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
    from app.services.marketing_email import render_for_recipient

    class FakeRanking:
        overall_score = 82.7

    html = render_for_recipient(
        "<p>Score: {{score}}</p><a href='{{cta_url}}'>CTA</a>"
        "<a href='{{unsubscribe_url}}'>Unsub</a><p>{{company_address}}</p>",
        FakeRanking(),
        uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
        "https://example.com",
    )
    assert "Score: 83" in html
    assert "https://example.com/score/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" in html
    assert "/unsubscribe/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee?token=" in html
    assert "3965 Lewis Link" in html
