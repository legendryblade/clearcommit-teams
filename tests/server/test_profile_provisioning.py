"""Profile provisioning at the dependency boundary.

Supabase issues tokens for users who have no local profile row yet. A route
must never reach an INSERT that references a missing profile: PostgreSQL
enforces the foreign key even though SQLite did not, which is how this bug
first surfaced. These tests act with a token that has never called
/api/auth/me.
"""

from __future__ import annotations

import time

import jwt
import pytest


def test_supabase_token_can_act_before_auth_me(client, monkeypatch) -> None:
    """A fresh Supabase identity can create an org without visiting /me first."""
    from server.config import load_settings
    from server.security import TokenService

    pytest.importorskip("cryptography")

    secret = "provisioning-test-secret-value-32-bytes"
    settings = load_settings(
        {
            "CLEARCOMMIT_SUPABASE_URL": "https://example.supabase.co",
            "CLEARCOMMIT_SUPABASE_JWT_SECRET": secret,
            "CLEARCOMMIT_DATABASE_URL": client.app.state.settings.database_url,
            "CLEARCOMMIT_SERVER_DATA_DIR": str(
                client.app.state.settings.server_data_dir
            ),
        }
    )
    # Swap the verifier only for this test, and always restore it so later
    # tests are not silently run in Supabase mode.
    original_tokens = client.app.state.tokens
    monkeypatch.setattr(client.app.state, "tokens", TokenService(settings), raising=False)

    now = int(time.time())
    token = jwt.encode(
        {
            "sub": "aaaaaaaa-1111-2222-3333-444444444444",
            "aud": "authenticated",
            "iat": now,
            "exp": now + 600,
            "email": "fresh.supabase.user@example.com",
        },
        secret,
        algorithm="HS256",
    )
    headers = {"Authorization": f"Bearer {token}"}

    # Never call /api/auth/me. Create an organization directly.
    created = client.post("/api/orgs", json={"name": "Provisioned Org"}, headers=headers)
    assert created.status_code == 200, created.text
    assert created.json()["ok"] is True

    # The audit row referencing the actor exists, so provisioning happened.
    org_id = created.json()["data"]["org_id"]
    audit = client.get(f"/api/orgs/{org_id}/audit", headers=headers)
    assert audit.status_code == 200
    assert audit.json()["data"]["events"], "audit trail should record org creation"

    # And /me now reports the same identity, with the row already present.
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["data"]["profile"]["email"] == "fresh.supabase.user@example.com"
