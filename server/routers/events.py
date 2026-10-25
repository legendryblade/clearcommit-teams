"""Authenticated real-time event stream.

The token is verified before the socket is accepted. A client is subscribed
only to the organizations its verified session belongs to; the client cannot
choose an organization to listen to. Payloads carry no transcript content.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from ..db import create_db_engine, make_session_factory  # noqa: F401  (documented import surface)
from ..models import Membership
from ..security import AuthError

router = APIRouter(tags=["events"])


@router.websocket("/ws")
async def events_socket(websocket: WebSocket, token: str = Query(default="")):
    app = websocket.app
    tokens = app.state.tokens
    try:
        principal = tokens.verify(token)
    except AuthError:
        await websocket.accept()
        await websocket.close(code=4401, reason="invalid_token")
        return

    def active_orgs() -> list[str]:
        session = app.state.session_factory()
        try:
            return [
                row[0]
                for row in session.query(Membership.org_id)
                .filter(Membership.user_id == principal.user_id, Membership.status == "active")
                .all()
            ]
        finally:
            session.close()

    org_ids = active_orgs()
    await websocket.accept()
    await app.state.hub.subscribe(org_ids, principal.user_id, websocket)
    try:
        while True:
            message = await websocket.receive_text()
            if message.strip() == "ping":
                # Recompute membership so the client can detect a changed
                # subscription (joined, invited, or revoked) and reconnect.
                current = active_orgs()
                await websocket.send_text(
                    json.dumps({"type": "pong", "orgs": current, "changed": current != org_ids})
                )
    except WebSocketDisconnect:
        pass
    finally:
        app.state.hub.unsubscribe(websocket)
