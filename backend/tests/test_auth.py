"""The API rejects requests without a valid Supabase access token."""

import pytest
from fastapi.testclient import TestClient

from app.auth import verify_token
from app.main import app
from tests.conftest import FAKE_CLAIMS

client = TestClient(app)


@pytest.fixture
def no_auth_override():
    """Restore the real verify_token dependency for one test."""
    app.dependency_overrides.pop(verify_token, None)
    yield
    app.dependency_overrides[verify_token] = lambda: FAKE_CLAIMS


def test_health_is_public(no_auth_override):
    assert client.get("/api/health").status_code == 200


@pytest.mark.parametrize("path", ["/api/meta", "/api/teams", "/api/player-stats"])
def test_missing_token_is_rejected(no_auth_override, path):
    assert client.get(path).status_code == 401


def test_garbage_token_is_rejected(no_auth_override):
    r = client.get("/api/meta", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401


def test_authenticated_request_passes():
    # The suite-wide override stands in for a verified token.
    assert client.get("/api/meta").status_code == 200
