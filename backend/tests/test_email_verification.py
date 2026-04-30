import hashlib
import hmac
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import pytest_asyncio

from app.config import settings


# Override the autouse setup_db fixture from conftest so these pure unit tests
# don't require a running PostgreSQL instance.
@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    yield None


@pytest.mark.asyncio
async def test_verify_with_hunter_returns_status_and_suggestion():
    """Hunter.io returns verification result with optional suggested email."""
    from app.services.email_verification import verify_with_hunter

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": {
            "status": "valid",
            "result": "deliverable",
            "email": "john@acme.com",
        }
    }

    with patch("app.services.email_verification.httpx.AsyncClient") as MockClient:
        client_instance = AsyncMock()
        client_instance.get = AsyncMock(return_value=mock_response)
        client_instance.__aenter__ = AsyncMock(return_value=client_instance)
        client_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = client_instance

        result = await verify_with_hunter("john@acme.com", "John", "Doe", "Acme Inc")

    assert result["status"] == "valid"
    assert result["suggested_email"] is None


@pytest.mark.asyncio
async def test_verify_with_hunter_returns_corrected_email():
    """Hunter.io returns a different email than what was submitted."""
    from app.services.email_verification import verify_with_hunter

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": {
            "status": "valid",
            "result": "deliverable",
            "email": "j.doe@acme.com",
        }
    }

    with patch("app.services.email_verification.httpx.AsyncClient") as MockClient:
        client_instance = AsyncMock()
        client_instance.get = AsyncMock(return_value=mock_response)
        client_instance.__aenter__ = AsyncMock(return_value=client_instance)
        client_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = client_instance

        result = await verify_with_hunter("john@acme.com", "John", "Doe", "Acme Inc")

    assert result["status"] == "valid"
    assert result["suggested_email"] == "j.doe@acme.com"


@pytest.mark.asyncio
async def test_verify_with_neverbounce_returns_result():
    """NeverBounce returns validation result."""
    from app.services.email_verification import verify_with_neverbounce

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "result": "valid",
        "flags": ["has_dns", "has_dns_mx"],
    }

    with patch("app.services.email_verification.httpx.AsyncClient") as MockClient:
        client_instance = AsyncMock()
        client_instance.get = AsyncMock(return_value=mock_response)
        client_instance.__aenter__ = AsyncMock(return_value=client_instance)
        client_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = client_instance

        result = await verify_with_neverbounce("john@acme.com")

    assert result["result"] == "valid"


def test_generate_unsubscribe_url():
    """Unsubscribe URL contains investor_id and valid HMAC token."""
    from app.services.email_verification import generate_unsubscribe_url

    investor_id = "550e8400-e29b-41d4-a716-446655440000"
    url = generate_unsubscribe_url(investor_id, "https://www.deepthesis.co")

    assert f"/unsubscribe/{investor_id}" in url
    assert "token=" in url

    token = url.split("token=")[1]
    expected = hmac.new(
        settings.jwt_secret.encode(), investor_id.encode(), hashlib.sha256
    ).hexdigest()
    assert token == expected


def test_verify_unsubscribe_token_valid():
    """Valid HMAC token passes verification."""
    from app.services.email_verification import verify_unsubscribe_token

    investor_id = "550e8400-e29b-41d4-a716-446655440000"
    token = hmac.new(
        settings.jwt_secret.encode(), investor_id.encode(), hashlib.sha256
    ).hexdigest()

    assert verify_unsubscribe_token(investor_id, token) is True


def test_verify_unsubscribe_token_invalid():
    """Invalid HMAC token fails verification."""
    from app.services.email_verification import verify_unsubscribe_token

    assert verify_unsubscribe_token("some-id", "bad-token") is False
