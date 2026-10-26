/* ClearCommit Teams — network client for the shared team workspace.
 *
 * Talks to the FastAPI backend over HTTP with a bearer token and subscribes
 * to the authenticated event stream. It never holds privileged credentials;
 * the token it stores is the signed session token issued by the backend
 * (demo mode) or Supabase Auth (Supabase mode).
 */
(function () {
  "use strict";

  const TOKEN_KEY = "clearcommit.teams.token";
  const SERVER_KEY = "clearcommit.teams.server";
  const SUPABASE_KEY = "clearcommit.teams.supabase";

  // The API base URL is configuration, not a constant. Resolution order:
  //   1. an explicit choice saved by the user (the server field in the UI)
  //   2. a value injected by the host page (window.CLEARCOMMIT_API_BASE)
  //   3. the local development default
  // A deployed build sets (2) so no private address is baked into the app.
  const DEV_DEFAULT = "http://127.0.0.1:8770";

  function configuredDefault() {
    const injected = typeof window !== "undefined" ? window.CLEARCOMMIT_API_BASE : null;
    if (injected && String(injected).trim()) return String(injected).trim().replace(/\/+$/, "");
    return DEV_DEFAULT;
  }

  function serverUrl() {
    const stored = localStorage.getItem(SERVER_KEY);
    return (stored && stored.trim() ? stored.trim() : configuredDefault()).replace(/\/+$/, "");
  }

  function setServer(url) {
    if (url && url.trim()) localStorage.setItem(SERVER_KEY, url.trim().replace(/\/+$/, ""));
    else localStorage.removeItem(SERVER_KEY);
  }

  function token() {
    return localStorage.getItem(TOKEN_KEY) || "";
  }

  function setToken(value) {
    if (value) localStorage.setItem(TOKEN_KEY, value);
    else localStorage.removeItem(TOKEN_KEY);
  }

  function signedIn() {
    return Boolean(token());
  }

  function httpError(code, message, extra) {
    const error = new Error(message || "The request could not be completed.");
    error.code = code || "request_failed";
    if (extra) Object.assign(error, extra);
    return error;
  }

  async function call(method, path, body) {
    const headers = { "Content-Type": "application/json" };
    if (token()) headers.Authorization = "Bearer " + token();
    let response;
    try {
      response = await fetch(serverUrl() + path, {
        method: method,
        headers: headers,
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch (cause) {
      throw httpError("network_error", "The team server is unreachable.", {
        retryable: true,
        cause: cause,
      });
    }
    let payload = null;
    try {
      payload = await response.json();
    } catch (cause) {
      throw httpError("bad_response", "The team server returned an unreadable response.");
    }
    if (!payload || payload.ok !== true) {
      const detail = (payload && payload.error) || {};
      if (response.status === 401) setToken("");
      throw httpError(detail.code || "request_failed", detail.message, {
        status: response.status,
        retryable: Boolean(detail.retryable),
        request_id: detail.request_id,
      });
    }
    return payload.data;
  }

  async function health() {
    try {
      const response = await fetch(serverUrl() + "/health", { method: "GET" });
      return response.ok;
    } catch (cause) {
      return false;
    }
  }

  /**
   * Which authentication mode the configured backend is running.
   * Returns "demo" or "supabase" (from /ready), or null when unreachable.
   */
  async function authMode() {
    try {
      const response = await fetch(serverUrl() + "/ready", { method: "GET" });
      if (!response.ok) return null;
      const payload = await response.json();
      if (!payload || payload.ok !== true) return null;
      return payload.mode === "supabase" ? "supabase" : "demo";
    } catch (cause) {
      return null;
    }
  }

  /**
   * Sign in. Demo mode posts to this backend; Supabase mode exchanges the
   * password for a Supabase Auth access token, which the backend then
   * verifies. The Supabase anon key is a public client key, never the
   * service-role key.
   */
  async function signIn(mode, credentials) {
    const email = (credentials.email || "").trim();
    const password = credentials.password || "";

    if (mode !== "supabase") {
      const data = await call("POST", "/api/auth/demo/sign-in", { email: email, password: password });
      setToken(data.token);
      return { mode: "demo", profile: data.profile };
    }

    const supabase = await supabaseConfig();
    if (!supabase.url || !supabase.anonKey) {
      throw httpError(
        "supabase_not_configured",
        "This backend uses Supabase Auth but the client has no Supabase URL/anon key configured."
      );
    }
    const response = await fetch(supabase.url + "/auth/v1/token?grant_type=password", {
      method: "POST",
      headers: { "Content-Type": "application/json", apikey: supabase.anonKey },
      body: JSON.stringify({ email: email, password: password }),
    });
    const payload = await response.json().catch(function () { return null; });
    if (!response.ok || !payload || !payload.access_token) {
      const message = (payload && (payload.error_description || payload.msg || payload.error)) ||
        "Supabase rejected those credentials.";
      throw httpError("invalid_credentials", message, { status: response.status });
    }
    setToken(payload.access_token);
    const me = await call("GET", "/api/auth/me");
    return { mode: "supabase", profile: me.profile };
  }

  async function signUp(mode, credentials) {
    if (mode !== "supabase") {
      const data = await call("POST", "/api/auth/demo/sign-up", {
        email: (credentials.email || "").trim(),
        display_name: (credentials.displayName || "").trim(),
        password: credentials.password || "",
      });
      setToken(data.token);
      return { mode: "demo", profile: data.profile, needsConfirmation: false };
    }
    const supabase = await supabaseConfig();
    if (!supabase.url || !supabase.anonKey) {
      throw httpError(
        "supabase_not_configured",
        "This backend uses Supabase Auth but the client has no Supabase URL/anon key configured."
      );
    }
    const response = await fetch(supabase.url + "/auth/v1/signup", {
      method: "POST",
      headers: { "Content-Type": "application/json", apikey: supabase.anonKey },
      body: JSON.stringify({
        email: (credentials.email || "").trim(),
        password: credentials.password || "",
        data: { display_name: (credentials.displayName || "").trim() },
      }),
    });
    const payload = await response.json().catch(function () { return null; });
    if (!response.ok || !payload) {
      const message = (payload && (payload.error_description || payload.msg || payload.error)) ||
        "Supabase could not create that account.";
      throw httpError("signup_failed", message, { status: response.status });
    }
    if (payload.access_token) {
      setToken(payload.access_token);
      const me = await call("GET", "/api/auth/me");
      return { mode: "supabase", profile: me.profile, needsConfirmation: false };
    }
    return { mode: "supabase", profile: null, needsConfirmation: true };
  }

  function supabaseLocation() {
    const stored = localStorage.getItem(SUPABASE_KEY) || "";
    if (!stored) return { url: "", anonKey: "" };
    try {
      return JSON.parse(stored);
    } catch (cause) {
      return { url: "", anonKey: "" };
    }
  }

  function setSupabaseLocation(url, anonKey) {
    if (url && anonKey) {
      localStorage.setItem(
        SUPABASE_KEY,
        JSON.stringify({ url: String(url).replace(/\/+$/, ""), anonKey: String(anonKey) })
      );
    } else {
      localStorage.removeItem(SUPABASE_KEY);
    }
  }

  async function supabaseConfig() {
    const local = supabaseLocation();
    if (local.url && local.anonKey) return local;
    // Fall back to values the backend can safely expose (URL + public anon key).
    try {
      const response = await fetch(serverUrl() + "/api/auth/config", { method: "GET" });
      if (response.ok) {
        const payload = await response.json();
        if (payload && payload.ok === true) {
          return { url: payload.data.supabase_url || "", anonKey: payload.data.anon_key || "" };
        }
      }
    } catch (cause) {
      /* fall through */
    }
    return { url: "", anonKey: "" };
  }

  function signOutRemote(mode) {
    setToken("");
    if (mode === "supabase") {
      // Best effort only: the local token is already discarded.
      void supabaseConfig().then(function (supabase) {
        if (!supabase.url) return;
        void fetch(supabase.url + "/auth/v1/logout", {
          method: "POST",
          headers: { apikey: supabase.anonKey, Authorization: "Bearer " + token() },
        }).catch(function () {});
      });
    }
  }

  function connect(handlers) {
    const options = handlers || {};
    let socket = null;
    let stopped = false;
    let attempt = 0;
    let timer = null;
    let pingTimer = null;

    function setStatus(status, detail) {
      if (options.onStatus) options.onStatus(status, detail);
    }

    function schedule() {
      if (stopped) return;
      attempt += 1;
      const delay = Math.min(30000, 1000 * Math.pow(2, Math.min(attempt, 5)));
      setStatus("reconnecting", { retry_in_ms: delay });
      timer = window.setTimeout(open, delay);
    }

    function open() {
      if (stopped) return;
      if (!token()) {
        setStatus("signed_out");
        return;
      }
      const url = serverUrl().replace(/^http/, "ws") + "/ws?token=" + encodeURIComponent(token());
      try {
        socket = new WebSocket(url);
      } catch (cause) {
        schedule();
        return;
      }
      socket.addEventListener("open", function () {
        attempt = 0;
        setStatus("online");
        pingTimer = window.setInterval(function () {
          if (socket && socket.readyState === WebSocket.OPEN) socket.send("ping");
        }, 8000);
      });
      socket.addEventListener("message", function (event) {
        let message = null;
        try {
          message = JSON.parse(event.data);
        } catch (cause) {
          return;
        }
        if (message && message.type === "pong") {
          // The server recomputes membership on ping. If it changed, this
          // socket's subscription is stale, so reconnect to resubscribe.
          if (message.changed) {
            socket.close(4000, "resubscribe");
            schedule();
          }
          return;
        }
        if (options.onEvent) options.onEvent(message);
      });
      socket.addEventListener("close", function (event) {
        if (pingTimer) window.clearInterval(pingTimer);
        pingTimer = null;
        socket = null;
        if (stopped) return;
        if (event.code === 4401) {
          setStatus("unauthorized");
          return;
        }
        schedule();
      });
      socket.addEventListener("error", function () {
        /* close handler drives the retry */
      });
    }

    open();

    return {
      close: function () {
        stopped = true;
        if (timer) window.clearTimeout(timer);
        if (pingTimer) window.clearInterval(pingTimer);
        if (socket) socket.close();
        socket = null;
      },
      reconnect: function () {
        stopped = false;
        attempt = 0;
        if (timer) window.clearTimeout(timer);
        if (socket) {
          try {
            socket.close();
          } catch (cause) {
            /* ignore */
          }
        }
        open();
      },
    };
  }

  window.ClearCommitNet = {
    authMode: authMode,
    signIn: signIn,
    signUp: signUp,
    signOutRemote: signOutRemote,
    supabaseLocation: supabaseLocation,
    setSupabaseLocation: setSupabaseLocation,
    call: call,
    connect: connect,
    health: health,
    serverUrl: serverUrl,
    setServer: setServer,
    token: token,
    setToken: setToken,
    signedIn: signedIn,
    DEFAULT_SERVER: configuredDefault(),
  };
})();
