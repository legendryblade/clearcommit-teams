from __future__ import annotations

import json
import sys
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from clearcommit_teams.devserver import make_server


@pytest.fixture
def dev_server(ctx, data_dir):
    ui_dir = data_dir / "ui-fixture"
    ui_dir.mkdir()
    (ui_dir / "index.html").write_text("<!doctype html><title>Fixture</title>", encoding="utf-8")
    server = make_server(0, ctx.bridge, directory=ui_dir)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def post_json(base_url: str, method: str, payload):
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        f"{base_url}/api/{method}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_devserver_serves_ui_with_security_headers(dev_server) -> None:
    with urlopen(dev_server + "/", timeout=5) as response:
        assert response.status == 200
        html = response.read().decode("utf-8")
        assert "Fixture" in html
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        assert "default-src 'self'" in response.headers["Content-Security-Policy"]
        assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_devserver_calls_the_real_bridge(dev_server) -> None:
    status, envelope = post_json(dev_server, "bootstrap", {})
    assert status == 200
    assert envelope["ok"] is True
    assert envelope["data"]["app"]["name"] == "ClearCommit Teams"
    assert len(envelope["data"]["sessions"]) == 3


def test_devserver_exposes_only_public_methods(dev_server) -> None:
    status, envelope = post_json(dev_server, "_bootstrap", {})
    assert status == 404
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "unknown_method"


def test_devserver_rejects_invalid_json(dev_server) -> None:
    request = Request(
        dev_server + "/api/bootstrap",
        data=b"{not json",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(HTTPError) as excinfo:
        urlopen(request, timeout=5)
    assert excinfo.value.code == 400
    envelope = json.loads(excinfo.value.read().decode("utf-8"))
    assert envelope["error"]["code"] == "invalid_json"


def test_devserver_returns_typed_bridge_errors(dev_server) -> None:
    status, envelope = post_json(dev_server, "get_session", {"session_id": "s_missing"})
    assert status == 200
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "not_found"


def test_devserver_serves_requests_without_a_console(dev_server, monkeypatch) -> None:
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    with urlopen(dev_server + "/", timeout=5) as response:
        assert response.status == 200
    status, envelope = post_json(dev_server, "bootstrap", {})
    assert status == 200
    assert envelope["ok"] is True


def test_devserver_rejects_non_api_posts(dev_server) -> None:
    request = Request(
        dev_server + "/elsewhere",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(HTTPError) as excinfo:
        urlopen(request, timeout=5)
    assert excinfo.value.code == 404
