"""Bypass Supabase JWT verification for the whole test suite.

test_auth.py removes the override to exercise the real dependency.
"""

from app.auth import verify_token
from app.main import app

FAKE_CLAIMS = {"sub": "00000000-0000-0000-0000-000000000000", "role": "authenticated"}

app.dependency_overrides[verify_token] = lambda: FAKE_CLAIMS
