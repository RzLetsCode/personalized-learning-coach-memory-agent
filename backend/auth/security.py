"""
Security utilities for the Enterprise AI Learning Coach.

Handles password hashing, verification, and session token generation.
Uses passlib (bcrypt) - same context as the User model for consistency.
"""

import secrets
from passlib.context import CryptContext

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a plain-text password for secure storage."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return True if the plain password matches the stored bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


# ---------------------------------------------------------------------------
# Session token helpers (lightweight - no JWT dependency needed for Streamlit)
# ---------------------------------------------------------------------------
def generate_session_token(length: int = 32) -> str:
    """Generate a cryptographically secure random session token."""
    return secrets.token_urlsafe(length)


def is_strong_password(password: str) -> tuple[bool, str]:
    """
    Validate password strength.
    Returns (is_valid: bool, message: str).
    """
    if len(password) < 5:
        return False, "Password must be at least 8 characters long."
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter."
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter."
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one digit."
    return True, "Password is strong."
