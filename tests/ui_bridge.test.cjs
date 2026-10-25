"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { createBridge, BridgeCallError } = require("../ui/js/bridge.js");

function apiWith(handlers) {
  return new Proxy(handlers, {
    get(target, property) {
      if (property in target) {
        return target[property];
      }
      return undefined;
    },
  });
}

test("api transport unwraps a successful envelope", async () => {
  const calls = [];
  const api = apiWith({
    bootstrap: async (payload) => {
      calls.push(payload);
      return { ok: true, data: { app: { name: "ClearCommit Teams" } } };
    },
  });
  const bridge = createBridge({ api: api });
  const data = await bridge.call("bootstrap", { hello: true });
  assert.equal(data.app.name, "ClearCommit Teams");
  assert.deepEqual(calls, [{ hello: true }]);
  assert.equal(bridge.transport(), "api");
});

test("api transport accepts a JSON string envelope", async () => {
  const api = apiWith({
    ping: async () => JSON.stringify({ ok: true, data: { name: "ClearCommit Teams" } }),
  });
  const bridge = createBridge({ api: api });
  const data = await bridge.call("ping");
  assert.equal(data.name, "ClearCommit Teams");
});

test("typed bridge errors keep code, retryability and detail", async () => {
  const api = apiWith({
    analyze: async () => ({
      ok: false,
      error: {
        code: "insufficient_evidence",
        message: "Select at least one utterance.",
        retryable: false,
        detail: { missing: [] },
      },
    }),
  });
  const bridge = createBridge({ api: api });
  await assert.rejects(
    () => bridge.call("analyze", { evidence_refs: [] }),
    (error) => {
      assert.ok(error instanceof BridgeCallError);
      assert.equal(error.code, "insufficient_evidence");
      assert.equal(error.retryable, false);
      assert.deepEqual(error.detail, { missing: [] });
      return true;
    }
  );
});

test("malformed envelopes are rejected as protocol errors", async () => {
  for (const value of ["not json", { nope: true }, [], null]) {
    const api = apiWith({ ping: async () => value });
    const bridge = createBridge({ api: api });
    await assert.rejects(
      () => bridge.call("ping"),
      (error) => error instanceof BridgeCallError && error.code === "bridge_protocol"
    );
  }
});

test("unknown methods never reach the bridge", async () => {
  let called = false;
  const api = apiWith({
    _bootstrap: async () => {
      called = true;
      return { ok: true, data: {} };
    },
  });
  const bridge = createBridge({ api: api });
  await assert.rejects(
    () => bridge.call("_bootstrap"),
    (error) => error.code === "unknown_method"
  );
  assert.equal(called, false);
});

test("missing api methods are reported as unknown methods", async () => {
  const bridge = createBridge({ api: apiWith({}) });
  await assert.rejects(
    () => bridge.call("test_provider"),
    (error) => error.code === "unknown_method"
  );
});

test("http transport posts to the loopback API and unwraps", async () => {
  const requests = [];
  const fetchImpl = async (url, options) => {
    requests.push({ url, options });
    return {
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ ok: true, data: { mode: "mock" } }),
    };
  };
  const bridge = createBridge({
    fetchImpl: fetchImpl,
    location: { protocol: "http:", href: "http://127.0.0.1:8765/" },
  });
  const data = await bridge.call("provider_status", {});
  assert.deepEqual(data, { mode: "mock" });
  assert.equal(requests[0].url, "/api/provider_status");
  assert.equal(requests[0].options.method, "POST");
  assert.equal(requests[0].options.body, "{}");
});

test("http error envelopes keep their typed code", async () => {
  const fetchImpl = async () => ({
    ok: false,
    status: 404,
    text: async () => JSON.stringify({
      ok: false,
      error: { code: "unknown_method", message: "Not available", retryable: false },
    }),
  });
  const bridge = createBridge({
    fetchImpl: fetchImpl,
    location: { protocol: "http:", href: "http://127.0.0.1:8765/" },
  });
  await assert.rejects(
    () => bridge.call("get_session", { session_id: "x" }),
    (error) => error.code === "unknown_method"
  );
});

test("network failures are retryable and do not leak the exception", async () => {
  const fetchImpl = async () => {
    throw new Error("connect ECONNREFUSED 127.0.0.1:8765");
  };
  const bridge = createBridge({
    fetchImpl: fetchImpl,
    location: { protocol: "http:", href: "http://127.0.0.1:8765/" },
  });
  await assert.rejects(
    () => bridge.call("bootstrap"),
    (error) => {
      assert.equal(error.code, "network_error");
      assert.equal(error.retryable, true);
      assert.equal(error.message.includes("ECONNREFUSED"), false);
      return true;
    }
  );
});

test("http timeouts abort and report bridge_timeout", async () => {
  const fetchImpl = (url, options) => new Promise((resolve, reject) => {
    options.signal.addEventListener("abort", () => {
      const error = new Error("aborted");
      error.name = "AbortError";
      reject(error);
    });
  });
  const bridge = createBridge({
    fetchImpl: fetchImpl,
    location: { protocol: "http:", href: "http://127.0.0.1:8765/" },
    timeoutMs: 20,
  });
  await assert.rejects(
    () => bridge.call("bootstrap"),
    (error) => error.code === "bridge_timeout" && error.retryable === true
  );
});

test("file pages wait for pywebviewready before using the bridge", async () => {
  const listeners = {};
  const fakeWindow = {
    location: { protocol: "file:", href: "file:///app/index.html" },
    addEventListener(event, handler) {
      listeners[event] = handler;
    },
  };
  const bridge = createBridge({ windowObject: fakeWindow });
  const pending = bridge.call("ping");
  await new Promise((resolve) => setTimeout(resolve, 10));
  fakeWindow.pywebview = {
    api: {
      ping: async () => ({ ok: true, data: { ready: true } }),
    },
  };
  listeners.pywebviewready();
  const data = await pending;
  assert.equal(data.ready, true);
  assert.equal(bridge.transport(), "api");
});

test("file pages report bridge_not_ready instead of guessing", async () => {
  const fakeWindow = {
    location: { protocol: "file:", href: "file:///app/index.html" },
    addEventListener() {},
  };
  const bridge = createBridge({ windowObject: fakeWindow, apiWaitMs: 25 });
  await assert.rejects(
    () => bridge.call("ping"),
    (error) => error.code === "bridge_not_ready" && error.retryable === true
  );
});
