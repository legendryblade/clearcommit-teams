"""Shared fixtures for the network backend tests.

These tests run against the real FastAPI app with a real database (SQLite in
demo mode, PostgreSQL when configured). Nothing here mocks the service layer:
the HTTP boundary, auth, authorization and persistence are all exercised.

Mock-only tests, where any exist, are named test_mock_* and marked.
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

from server.config import load_settings
from server.main import create_app


@pytest.fixture(scope="session")
def app_settings(tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("server-data")
    env = {
        "CLEARCOMMIT_SERVER_DATA_DIR": str(data_dir),
        "CLEARCOMMIT_DATABASE_URL": f"sqlite:///{(data_dir / 'test.db').as_posix()}",
    }
    # Ignore any Supabase configuration in the ambient environment so these
    # tests are explicit about what they run against.
    for key in (
        "CLEARCOMMIT_SUPABASE_URL",
        "CLEARCOMMIT_SUPABASE_JWT_SECRET",
        "CLEARCOMMIT_SUPABASE_JWKS_URL",
    ):
        os.environ.pop(key, None)
    return load_settings(env)


@pytest.fixture(scope="session")
def app(app_settings):
    return create_app(app_settings)


@pytest.fixture()
def client(app):
    with TestClient(app) as test_client:
        yield test_client
    app.state.hub = type(app.state.hub)()


def unique_email(prefix: str) -> str:
    return f"{prefix}+{uuid.uuid4().hex[:10]}@example.com"


class Actor:
    """A signed-in caller with helpers for the common API calls."""

    def __init__(self, client: TestClient, token: str, profile: dict):
        self.client = client
        self.token = token
        self.profile = profile
        self.user_id = profile["user_id"]

    def call(self, method: str, path: str, body=None):
        headers = {"Authorization": f"Bearer {self.token}"}
        if method == "GET":
            return self.client.get(path, headers=headers)
        if method == "POST":
            return self.client.post(path, json=body if body is not None else {}, headers=headers)
        if method == "PATCH":
            return self.client.patch(path, json=body or {}, headers=headers)
        if method == "DELETE":
            return self.client.delete(path, headers=headers)
        raise ValueError(method)

    def data(self, method: str, path: str, body=None):
        response = self.call(method, path, body)
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["ok"] is True, payload
        return payload["data"]


@pytest.fixture()
def make_actor(client):
    def factory(prefix: str = "user", display_name: str | None = None) -> Actor:
        email = unique_email(prefix)
        response = client.post(
            "/api/auth/demo/sign-up",
            json={
                "email": email,
                "display_name": display_name or prefix.title(),
                "password": "test-password-1",
            },
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        return Actor(client, data["token"], data["profile"])

    return factory


@pytest.fixture()
def org_with_members(make_actor):
    """Owner + manager + sales_rep in one organization, plus conversations."""

    owner = make_actor("owner", "Olive Owner")
    manager = make_actor("manager", "Manny Manager")
    rep = make_actor("rep", "Riley Rep")

    org = owner.data("POST", "/api/orgs", {"name": "Acme Test Org"})
    org_id = org["org_id"]

    invitation = owner.data(
        "POST", f"/api/orgs/{org_id}/invitations", {"email": manager.profile["email"], "role": "manager"}
    )
    manager.data("POST", "/api/invitations/accept", {"invitation_id": invitation["invitation_id"]})

    rep_invitation = owner.data(
        "POST", f"/api/orgs/{org_id}/invitations", {"email": rep.profile["email"], "role": "sales_rep"}
    )
    rep.data("POST", "/api/invitations/accept", {"invitation_id": rep_invitation["invitation_id"]})

    conversation = rep.data("POST", f"/api/orgs/{org_id}/conversations", {"title": "Discovery call"})
    lines = rep.data(
        "POST",
        f"/api/orgs/{org_id}/conversations/{conversation['conversation_id']}/utterances",
        {
            "utterances": [
                {"speaker": "Customer", "content": "Who owns setup after we sign?"},
                {"speaker": "Rep", "content": "I think the team handles it."},
                {"speaker": "Customer", "content": "Can you confirm that in writing?"},
            ]
        },
    )
    return {
        "org_id": org_id,
        "owner": owner,
        "manager": manager,
        "rep": rep,
        "conversation_id": conversation["conversation_id"],
        "utterance_ids": [row["utterance_id"] for row in lines["utterances"]],
    }
