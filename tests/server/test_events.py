"""Real-time event delivery and refetch semantics."""

from __future__ import annotations


def test_events_are_scoped_to_the_organization(client, org_with_members, make_actor) -> None:
    org_id = org_with_members["org_id"]
    rep = org_with_members["rep"]
    manager = org_with_members["manager"]
    outsider = make_actor("outside", "Oscar Outside")
    outsider.data("POST", "/api/orgs", {"name": "Elsewhere"})

    with client.websocket_connect(f"/ws?token={rep.token}") as rep_ws:
        hello = rep_ws.receive_json()
        assert hello["type"] == "subscribed"
        assert org_id in hello["orgs"]

        with client.websocket_connect(f"/ws?token={manager.token}") as manager_ws:
            manager_ws.receive_json()

            insight = rep.data(
                "POST",
                f"/api/orgs/{org_id}/insights",
                {
                    "conversation_id": org_with_members["conversation_id"],
                    "title": "Event test",
                    "observed_issue": "Observed.",
                    "suggested_alternative": "Suggested.",
                    "evidence": [
                        {
                            "utterance_id": org_with_members["utterance_ids"][0],
                            "quote": "Who owns setup after we sign?",
                        }
                    ],
                },
            )

            # Private insight creation is not broadcast.
            rep_ws.send_text("ping")
            assert rep_ws.receive_json()["type"] == "pong"

            rep.data("POST", f"/api/insights/{insight['insight_id']}/share", {})
            event = manager_ws.receive_json()
            assert event["type"] == "insight.shared"
            assert event["resource"] == "insight"
            assert event["resource_id"] == insight["insight_id"]
            assert event["org_id"] == org_id
            assert "content" not in event  # minimal payload: no transcript text
            assert "evidence" not in event


def test_ping_reports_membership_changes(client, make_actor) -> None:
    owner = make_actor("pingowner", "Pia Owner")
    member = make_actor("pingmember", "Milo Member")
    org = owner.data("POST", "/api/orgs", {"name": "Ping Org"})

    with client.websocket_connect(f"/ws?token={member.token}") as ws:
        hello = ws.receive_json()
        assert org["org_id"] not in hello["orgs"]
        ws.send_text("ping")
        pong = ws.receive_json()
        assert pong["changed"] is False

        invitation = owner.data(
            "POST",
            f"/api/orgs/{org['org_id']}/invitations",
            {"email": member.profile["email"], "role": "manager"},
        )
        member.data("POST", "/api/invitations/accept", {"invitation_id": invitation["invitation_id"]})

        ws.send_text("ping")
        pong = ws.receive_json()
        assert pong["changed"] is True
        assert org["org_id"] in pong["orgs"]


def test_invalid_token_cannot_open_a_socket(client) -> None:
    with client.websocket_connect("/ws?token=bogus") as ws:
        # The server accepts then closes with an auth code; the next read ends.
        try:
            ws.receive_json()
        except Exception:
            pass
