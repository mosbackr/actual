from jose import JWTError, jwt

from app.config import settings


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token. Returns the payload dict."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def decode_token_or_none(token: str) -> dict | None:
    """Decode a JWT token, returning None if invalid."""
    try:
        return decode_token(token)
    except JWTError:
        return None
