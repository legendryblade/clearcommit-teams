"""Phase 4a: personal cloud records and desktop sync.

The acceptance claim: a record created for one account is readable from a
second session of that account, and from nowhere else. Duplicate syncs must
not create duplicate records.
"""

from __future__ import annotations


def test_personal_workspace_is_created_once(client, make_actor) -> None:
    user = make_actor("personal", "Pat Personal")

    first = user.data("POST", "/api/workspace")
    second = user.data("POST", "/api/workspace")

    assert first["org_id"] == second["org_id"]
    assert first["is_personal"] is True
    assert first["role"] == "owner"


def test_personal_workspace_is_not_listed_as_a_company(client, make_actor) -> None:
    user = make_actor("hidden", "Hana Hidden")
    workspace = user.data("POST", "/api/workspace")

    companies = user.data("GET", "/api/orgs")["organizations"]
    assert all(org["org_id"] != workspace["org_id"] for org in companies)


def test_personal_record_round_trips_and_is_private(client, make_actor) -> None:
    owner = make_actor("powner", "Perry Owner")
    stranger = make_actor("pstranger", "Sky Stranger")

    workspace = owner.data("POST", "/api/workspace")
    org_id = workspace["org_id"]

    conversation = owner.data(
        "POST",
        f"/api/orgs/{org_id}/conversations",
        {"title": "My personal call", "client_ref": "local-session-1", "source": "desktop"},
    )
    conversation_id = conversation["conversation_id"]

    lines = owner.data(
        "POST",
        f"/api/orgs/{org_id}/conversations/{conversation_id}/utterances",
        {
            "utterances": [
                {"speaker": "Customer", "content": "We need a security review."},
                {"speaker": "Rep", "content": "I will send the checklist today."},
            ]
        },
    )
    assert len(lines["utterances"]) == 2

    # The owner reads it back.
    fetched = owner.data("GET", f"/api/orgs/{org_id}/conversations/{conversation_id}")
    assert fetched["title"] == "My personal call"
    assert fetched["source"] == "desktop"
    assert len(fetched["utterances"]) == 2

    # A different account cannot, even with the real ids.
    assert (
        stranger.call("GET", f"/api/orgs/{org_id}/conversations/{conversation_id}").status_code
        == 404
    )
    assert stranger.call("GET", f"/api/orgs/{org_id}").status_code == 404
    assert stranger.call("GET", f"/api/orgs/{org_id}/conversations").status_code == 404


def test_repeated_sync_does_not_duplicate(client, make_actor) -> None:
    user = make_actor("sync", "Sam Sync")
    org_id = user.data("POST", "/api/workspace")["org_id"]

    first = user.data(
        "POST",
        f"/api/orgs/{org_id}/conversations",
        {"title": "Synced call", "client_ref": "same-local-id", "source": "desktop"},
    )
    second = user.data(
        "POST",
        f"/api/orgs/{org_id}/conversations",
        {"title": "Synced call", "client_ref": "same-local-id", "source": "desktop"},
    )

    assert first["conversation_id"] == second["conversation_id"]

    listing = user.data("GET", f"/api/orgs/{org_id}/conversations")["conversations"]
    assert len(listing) == 1


def test_two_sessions_of_one_account_see_the_same_personal_record(tmp_path) -> None:
    """A desktop session and a web session resolve to one record."""
    from fastapi.testclient import TestClient

    from server.config import load_settings
    from server.main import create_app

    settings = load_settings(
        {
            "CLEARCOMMIT_DATABASE_URL": f"sqlite:///{(tmp_path / 'phase4.db').as_posix()}",
            "CLEARCOMMIT_SERVER_DATA_DIR": str(tmp_path),
        }
    )
    app = create_app(settings)
    with TestClient(app) as client:
        token_service = client.app.state.tokens
        user_id = "12345678-1234-1234-1234-123456789abc"
        email = "two.sessions@example.com"
        desktop = token_service.issue_demo_token(user_id, email)
        web = token_service.issue_demo_token(user_id, email)

        desktop_headers = {"Authorization": f"Bearer {desktop}"}
        web_headers = {"Authorization": f"Bearer {web}"}

        workspace = client.post("/api/workspace", headers=desktop_headers).json()["data"]
        org_id = workspace["org_id"]

        created = client.post(
            f"/api/orgs/{org_id}/conversations",
            json={"title": "Desktop record", "client_ref": "d-1", "source": "desktop"},
            headers=desktop_headers,
        ).json()["data"]

        seen = client.get(
            f"/api/orgs/{org_id}/conversations/{created['conversation_id']}",
            headers=web_headers,
        )
        assert seen.status_code == 200, seen.text
        assert seen.json()["data"]["conversation_id"] == created["conversation_id"]


def test_personal_records_never_appear_in_a_company(client, make_actor) -> None:
    """A company listing must not leak an individual's private record."""
    user = make_actor("dual", "Dana Dual")
    personal = user.data("POST", "/api/workspace")

    company = user.data("POST", "/api/orgs", {"name": "Dana Ltd"})
    personal_conversation = user.data(
        "POST",
        f"/api/orgs/{personal['org_id']}/conversations",
        {"title": "Private record", "client_ref": "p-1", "source": "desktop"},
    )

    company_list = user.data("GET", f"/api/orgs/{company['org_id']}/conversations")
    assert all(
        row["conversation_id"] != personal_conversation["conversation_id"]
        for row in company_list["conversations"]
    )
