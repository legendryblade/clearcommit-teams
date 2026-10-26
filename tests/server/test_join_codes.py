"""Join codes: the code replaces handing someone a UUID.

The security property that matters: a code identifies the organization only.
It never grants a role by itself, and it never lets an unverified account in.
"""

from __future__ import annotations

from server.join_codes import normalise


def test_organization_gets_a_code_on_creation(client, make_actor) -> None:
    owner = make_actor("codeowner", "Cora Owner")
    org = owner.data("POST", "/api/orgs", {"name": "Code Co"})
    code = org.get("join_code")
    assert code
    assert len(code) == 8
    assert code.isalnum()
    # dictation-safe alphabet: no 0/O/1/I/L
    assert not set(code) & set("01OIL")
    assert org["join_code"] == normalise(code)


def test_join_with_code_alone(client, make_actor) -> None:
    owner = make_actor("joinowner", "Jo Owner")
    employee = make_actor("joinemp", "Em Employee")

    org = owner.data("POST", "/api/orgs", {"name": "Joinable Inc"})
    joined = employee.data("POST", "/api/join", {"code": org["join_code"]})

    assert joined["org_id"] == org["org_id"]
    assert joined["role"] == "sales_rep"  # least privilege
    assert employee.call("GET", f"/api/orgs/{org['org_id']}").status_code == 200


def test_code_is_forgiving_about_case_and_separators(client, make_actor) -> None:
    owner = make_actor("caseowner", "Case Owner")
    employee = make_actor("caseemp", "Case Emp")
    org = owner.data("POST", "/api/orgs", {"name": "Case Co"})
    code = org["join_code"]
    messy = (code[:4] + "-" + code[4:]).lower()
    assert employee.data("POST", "/api/join", {"code": messy})["org_id"] == org["org_id"]


def test_unknown_code_is_refused(client, make_actor) -> None:
    user = make_actor("nobody", "No Body")
    response = user.call("POST", "/api/join", {"code": "ZZZZZZZZ"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "invalid_code"


def test_code_does_not_grant_manager(client, make_actor) -> None:
    """A leaked code must not confer reviewer rights."""
    owner = make_actor("permowner", "Pat Owner")
    joiner = make_actor("permjoin", "Jules Joiner")
    org = owner.data("POST", "/api/orgs", {"name": "Perm Co"})
    membership = joiner.data("POST", "/api/join", {"code": org["join_code"]})

    assert membership["role"] == "sales_rep"
    draft = owner.data(
        "POST",
        f"/api/orgs/{org['org_id']}/playbook",
        {
            "title": "Needs review",
            "scenario": "s",
            "response": "r",
            "discovery_questions": ["q"],
        },
    )
    # A sales_rep cannot approve.
    assert (
        joiner.call("POST", f"/api/playbook/{draft['entry_id']}/approve", {}).status_code == 403
    )


def test_pending_invitation_sets_the_role(client, make_actor) -> None:
    owner = make_actor("invowner", "Ines Owner")
    invitee = make_actor("invited", "Ivan Invited")
    org = owner.data("POST", "/api/orgs", {"name": "Invite Co"})
    owner.data(
        "POST",
        f"/api/orgs/{org['org_id']}/invitations",
        {"email": invitee.profile["email"], "role": "manager"},
    )

    joined = invitee.data("POST", "/api/join", {"code": org["join_code"]})
    assert joined["role"] == "manager"


def test_rejoining_is_idempotent(client, make_actor) -> None:
    owner = make_actor("reowner", "Rae Owner")
    member = make_actor("remember", "Rex Member")
    org = owner.data("POST", "/api/orgs", {"name": "Repeat Co"})
    code = org["join_code"]

    first = member.data("POST", "/api/join", {"code": code})
    second = member.data("POST", "/api/join", {"code": code})
    assert first["membership_id"] == second["membership_id"]

    detail = owner.data("GET", f"/api/orgs/{org['org_id']}")
    assert len(detail["members"]) == 2


def test_personal_workspace_cannot_be_joined_by_code(client, make_actor) -> None:
    user = make_actor("solo", "Sol O")
    other = make_actor("solo2", "Sol Two")
    workspace = user.data("POST", "/api/workspace")
    # Personal workspaces have no join code at all.
    assert workspace.get("is_personal") is True
    assert not workspace.get("join_code")
    response = other.call("POST", "/api/join", {"code": "AAAAAAAA"})
    assert response.status_code == 404


def test_normalise_handles_whitespace_and_dashes() -> None:
    assert normalise(" skpx-tnpq ") == "SKPXTNPQ"
    assert normalise("") == ""
    assert normalise(None) == ""
