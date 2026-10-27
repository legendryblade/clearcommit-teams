/* ClearCommit Teams bridge client.
 *
 * The same transport is used by the pywebview desktop shell (window.pywebview.api)
 * and the loopback development server (POST /api/<method>). Every reply must be a
 * typed envelope: {ok:true,data} or {ok:false,error:{code,message,retryable}}.
 */
(function (root, factory) {
  "use strict";
  var api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  if (root) {
    root.ClearCommitBridge = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const METHODS = Object.freeze([
    "ping",
    "bootstrap",
    "list_sessions",
    "get_session",
    "create_session",
    "add_utterance",
    "import_transcript",
    "list_insights",
    "get_insight",
    "analyze",
    "ask_assistant",
    "list_assistant_notes",
    "list_playbook",
    "get_playbook",
    "create_playbook",
    "save_playbook",
    "approve_playbook",
    "save_settings",
    "provider_status",
    "test_provider",
    "refresh_preview",
    "use_workspace",
    "get_cloud_link",
    "set_cloud_link",
    "transcript_payload",
    "audio_status",
    "audio_devices",
    "audio_start",
    "audio_poll",
    "audio_stop",
    "interpret_status",
    "interpret",
  ]);

  const METHOD_SET = new Set(METHODS);
  const DEFAULT_TIMEOUT_MS = 60000;
  const API_WAIT_MS = 5000;

  class BridgeCallError extends Error {
    constructor(code, message, options) {
      super(message || "The local bridge could not complete that request.");
      this.name = "BridgeCallError";
      this.code = code || "bridge_error";
      this.retryable = Boolean(options && options.retryable);
      this.detail = options && options.detail !== undefined ? options.detail : null;
      this.status = options && options.status ? options.status : 0;
    }
  }

  function isObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function parseJson(text, method) {
    try {
      return JSON.parse(text);
    } catch (error) {
      throw new BridgeCallError(
        "bridge_protocol",
        "The local bridge returned a response that was not valid JSON.",
        { detail: { method: method } }
      );
    }
  }

  function unwrap(value, method) {
    let envelope = value;
    if (typeof envelope === "string") {
      envelope = parseJson(envelope, method);
    }
    if (!isObject(envelope) || typeof envelope.ok !== "boolean") {
      throw new BridgeCallError(
        "bridge_protocol",
        "The local bridge returned an unexpected response shape.",
        { detail: { method: method } }
      );
    }
    if (!envelope.ok) {
      const payload = isObject(envelope.error) ? envelope.error : {};
      throw new BridgeCallError(
        payload.code || "bridge_error",
        payload.message || "The local bridge could not complete that request.",
        {
          retryable: payload.retryable === true,
          detail: payload.detail === undefined ? null : payload.detail,
        }
      );
    }
    return envelope.data;
  }

  function createBridge(options) {
    const opts = options || {};
    const win = opts.windowObject || (typeof window !== "undefined" ? window : globalThis);
    const location = opts.location || win.location || { protocol: "file:" };
    const protocol = String(location.protocol || "file:");
    const fetchImpl = opts.fetchImpl || (typeof win.fetch === "function" ? win.fetch.bind(win) : null);
    const timeoutMs = Number(opts.timeoutMs || DEFAULT_TIMEOUT_MS);
    const apiWaitMs = Number(opts.apiWaitMs || API_WAIT_MS);
    const basePath = opts.basePath || "/api/";
    let api = opts.api || null;
    let waiters = [];
    let waitTimer = null;

    function publishApi() {
      if (!api && win.pywebview && win.pywebview.api) {
        api = win.pywebview.api;
      }
      if (api && waiters.length) {
        const pending = waiters;
        waiters = [];
        if (waitTimer) {
          clearTimeout(waitTimer);
          waitTimer = null;
        }
        pending.forEach(function (resolve) {
          resolve(api);
        });
      }
    }

    if (!api && win.pywebview) {
      publishApi();
    }
    if (!api && typeof win.addEventListener === "function") {
      win.addEventListener("pywebviewready", publishApi);
    }

    function transport() {
      if (api) {
        return "api";
      }
      if (protocol === "http:" || protocol === "https:") {
        return "http";
      }
      return "waiting";
    }

    function waitForApi() {
      if (api) {
        publishApi();
        return Promise.resolve(api);
      }
      if (protocol !== "file:" && protocol !== "about:") {
        return Promise.resolve(null);
      }
      return new Promise(function (resolve, reject) {
        waiters.push(resolve);
        if (!waitTimer) {
          waitTimer = setTimeout(function () {
            if (!api) {
              waiters = [];
              waitTimer = null;
              reject(new BridgeCallError(
                "bridge_not_ready",
                "The desktop bridge did not become ready. Restart ClearCommit Teams or use the browser UI.",
                { retryable: true }
              ));
            }
          }, apiWaitMs);
        }
      });
    }

    function withTimeout(promise, method) {
      let timer = null;
      return new Promise(function (resolve, reject) {
        timer = setTimeout(function () {
          reject(new BridgeCallError(
            "bridge_timeout",
            "The local app took too long to answer. Try again.",
            { retryable: true, detail: { method: method } }
          ));
        }, timeoutMs);
        Promise.resolve(promise).then(
          function (value) {
            clearTimeout(timer);
            resolve(value);
          },
          function (error) {
            clearTimeout(timer);
            reject(error);
          }
        );
      });
    }

    async function callApi(method, payload) {
      const fn = api[method];
      if (typeof fn !== "function") {
        throw new BridgeCallError(
          "unknown_method",
          "That action is not available in this build.",
          { detail: { method: method } }
        );
      }
      let result;
      try {
        result = await withTimeout(fn.call(api, payload), method);
      } catch (error) {
        if (error instanceof BridgeCallError) {
          throw error;
        }
        throw new BridgeCallError(
          "bridge_error",
          "The desktop bridge could not complete that action.",
          { detail: { method: method } }
        );
      }
      return unwrap(result, method);
    }

    async function callHttp(method, payload) {
      if (typeof fetchImpl !== "function") {
        throw new BridgeCallError(
          "bridge_not_ready",
          "No local bridge is available in this page.",
          { retryable: true }
        );
      }
      let controller = null;
      let timedOut = false;
      let timer = null;
      if (typeof AbortController === "function") {
        controller = new AbortController();
        timer = setTimeout(function () {
          timedOut = true;
          controller.abort();
        }, timeoutMs);
      }
      let response;
      try {
        response = await fetchImpl(basePath + encodeURIComponent(method), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload || {}),
          credentials: "same-origin",
          signal: controller ? controller.signal : undefined,
        });
      } catch (error) {
        if (timedOut) {
          throw new BridgeCallError(
            "bridge_timeout",
            "The local app took too long to answer. Try again.",
            { retryable: true, detail: { method: method } }
          );
        }
        throw new BridgeCallError(
          "network_error",
          "Could not reach the local app server. Check that it is still running.",
          { retryable: true, detail: { method: method } }
        );
      } finally {
        if (timer) {
          clearTimeout(timer);
        }
      }
      let text;
      try {
        text = await response.text();
      } catch (error) {
        throw new BridgeCallError(
          "network_error",
          "The local app stopped responding while sending its answer.",
          { retryable: true }
        );
      }
      const envelope = parseJson(text || "{}", method);
      if (!response.ok && !isObject(envelope)) {
        throw new BridgeCallError(
          "bridge_protocol",
          "The local app returned an unexpected error response.",
          { status: response.status }
        );
      }
      const data = unwrap(envelope, method);
      if (!response.ok) {
        throw new BridgeCallError(
          "bridge_protocol",
          "The local app rejected the request.",
          { status: response.status }
        );
      }
      return data;
    }

    async function call(method, payload) {
      if (!METHOD_SET.has(method)) {
        throw new BridgeCallError(
          "unknown_method",
          "That action is not available in this build.",
          { detail: { method: String(method) } }
        );
      }
      const body = payload === undefined || payload === null ? {} : payload;
      if (api) {
        return callApi(method, body);
      }
      const ready = await waitForApi();
      if (ready) {
        return callApi(method, body);
      }
      if (protocol === "http:" || protocol === "https:") {
        return callHttp(method, body);
      }
      throw new BridgeCallError(
        "bridge_not_ready",
        "The desktop bridge is not ready yet. Wait a moment and try again.",
        { retryable: true }
      );
    }

    return {
      call: call,
      transport: transport,
      methods: METHODS,
    };
  }

  return {
    BridgeCallError: BridgeCallError,
    METHODS: METHODS,
    createBridge: createBridge,
  };
});
