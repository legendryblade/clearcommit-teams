"""Same account, two independent client sessions.

This is the milestone's central claim: one hosted identity can read the same
cloud record from two separate sessions, while a different account cannot.
Sessions are created independently (separate sign-in calls), which is what the
desktop and web clients each do.
"""

from __future__ import annotations

import time

import jwt

from server.config import load_settings
from server.security import TokenService


def _two_sessions(app):
    """Two independent bearer tokens for one identity, as two clients would hold."""
    service = app.state.tokens
    user_id = "aaaabbbb-cccc-dddd-eeee-ffff00001111"
    email = "shared.identity@example.com"
    first = service.issue_demo_token(user_id, email)
    second = service.issue_demo_token(user_id, email)
    return first, second, user_id


def test_same_account_reads_the_same_record_from_two_sessions(tmp_path) -> None:
    # A dedicated demo-mode app: this test is about sessions, not Supabase mode.
    from fastapi.testclient import TestClient

    from server.config import load_settings
    from server.main import create_app

    settings = load_settings(
        {
            "CLEARCOMMIT_DATABASE_URL": f"sqlite:///{(tmp_path / 'session.db').as_posix()}",
            "CLEARCOMMIT_SERVER_DATA_DIR": str(tmp_path),
        }
    )
    app = create_app(settings)
    with TestClient(app) as client:
        first, second, user_id = _two_sessions(client.app)
        a = {"Authorization": f"Bearer {first}"}
        b = {"Authorization": f"Bearer {second}"}

        created = client.post("/api/orgs", json={"name": "Two Session Org"}, headers=a)
        assert created.status_code == 200, created.text
        org_id = created.json()["data"]["org_id"]

        conversation = client.post(
            f"/api/orgs/{org_id}/conversations",
            json={"title": "Created on the desktop"},
            headers=a,
        )
        assert conversation.status_code == 200
        conversation_id = conversation.json()["data"]["conversation_id"]

        # The second session (the "web" client) reads the same record.
        seen = client.get(f"/api/orgs/{org_id}/conversations/{conversation_id}", headers=b)
        assert seen.status_code == 200, seen.text
        assert seen.json()["data"]["conversation_id"] == conversation_id
        assert seen.json()["data"]["is_mine"] is True

def test_a_different_account_cannot_read_that_record(client, make_actor) -> None:
    owner = make_actor("cloudowner", "Cloud Owner")
    other = make_actor("cloudother", "Cloud Other")

    org = owner.data("POST", "/api/orgs", {"name": "Cloud Owner Org"})
    conversation = owner.data(
        "POST", f"/api/orgs/{org['org_id']}/conversations", {"title": "Private call"}
    )

    assert (
        other.call(
            "GET",
            f"/api/orgs/{org['org_id']}/conversations/{conversation['conversation_id']}",
        ).status_code
        == 404
    )


def test_client_supplied_owner_is_ignored(client, make_actor) -> None:
    """Claiming someone else's id in the payload must not grant ownership."""
    victim = make_actor("victim", "Vic Tim")
    attacker = make_actor("attacker", "Ann Attacker")

    response = attacker.client.post(
        "/api/orgs",
        json={"name": "Attacker Org", "created_by": victim.user_id, "owner_id": victim.user_id},
        headers={"Authorization": f"Bearer {attacker.token}"},
    )
    assert response.status_code == 200
    org_id = response.json()["data"]["org_id"]

    members = attacker.data("GET", f"/api/orgs/{org_id}")
    owner_rows = [m for m in members["members"] if m["role"] == "owner"]
    assert len(owner_rows) == 1
    assert owner_rows[0]["user_id"] == attacker.user_id
