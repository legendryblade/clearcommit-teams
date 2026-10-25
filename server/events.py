"""Real-time event hub.

Authenticated WebSocket clients receive minimal events for the organizations
their verified session belongs to: event type, resource type/id, org id, and
actor id. No transcript content, credentials, or record payloads travel over
the socket; clients refetch the authoritative resource through the API.

Events are emitted only after the triggering write has committed. Duplicate,
delayed, or missed events are harmless because clients refetch on receipt.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
import threading
import uuid
from collections import defaultdict

from fastapi import WebSocket

log = logging.getLogger("clearcommit.server")


class EventHub:
    def __init__(self):
        self._lock = threading.Lock()
        self._members: dict[str, set[WebSocket]] = defaultdict(set)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._counters: dict[str, itertools.count] = defaultdict(itertools.count)

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        with self._lock:
            self._loop = loop

    async def subscribe(self, org_ids: list[str], user_id: str, socket: WebSocket) -> None:
        for org_id in org_ids:
            with self._lock:
                self._members[org_id].add(socket)
        await socket.send_json(
            {"type": "subscribed", "orgs": org_ids, "user_id": user_id}
        )

    def unsubscribe(self, socket: WebSocket) -> None:
        with self._lock:
            for sockets in self._members.values():
                sockets.discard(socket)

    def emit(self, org_id: str, event_type: str, resource: str, resource_id: str, actor_id: str) -> dict:
        event = {
            "id": uuid.uuid4().hex,
            "seq": next(self._counters[org_id]),
            "type": event_type,
            "resource": resource,
            "resource_id": resource_id,
            "org_id": org_id,
            "actor_id": actor_id,
        }
        with self._lock:
            sockets = list(self._members.get(org_id, ()))
            loop = self._loop
        if not sockets or loop is None or loop.is_closed():
            return event
        try:
            asyncio.run_coroutine_threadsafe(self._broadcast(sockets, event), loop)
        except RuntimeError:
            log.warning("event emit failed; clients will refetch on next poll")
        return event

    async def _broadcast(self, sockets: list[WebSocket], event: dict) -> None:
        payload = json.dumps(event)
        for socket in sockets:
            try:
                await socket.send_text(payload)
            except Exception:
                self.unsubscribe(socket)
