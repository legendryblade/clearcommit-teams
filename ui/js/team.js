/* ClearCommit Teams — Team workspace view (network mode).
 *
 * This view talks to the FastAPI backend. It is deliberately separate from
 * the local single-user workspace so the two are never confused: everything
 * shown here is server-authoritative and labeled by its sync state.
 */
(function () {
  "use strict";

  const net = window.ClearCommitNet;
  if (!net) return;

  // The local workspace bridge, exposed by app.js so this view can scope
  // personal data to the signed-in account.
  function localBridge() {
    return window.ClearCommitLocalBridge || null;
  }

  const dom = {};
  const state = {
    me: null,
    organizations: [],
    orgId: null,
    members: [],
    conversations: [],
    myInsights: [],
    sharedInsights: [],
    playbook: [],
    invitations: [],
    liveStatus: "signed_out",
    mode: null,
    offline: false,
    busy: false,
    lastEvent: null,
    sessionGeneration: 0,
    localWorkspaceKey: null,
    pendingInvitations: [],
    tab: "overview",
    memberView: null,
    commitmentsMine: [],
    commitmentsTeam: [],
  };

  let socket = null;

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function clear(node) {
    while (node && node.firstChild) node.removeChild(node.firstChild);
  }

  function announce(message, tone) {
    if (!dom.notice) return;
    dom.notice.textContent = message;
    dom.notice.className = "team-notice" + (tone ? " is-" + tone : "");
    dom.notice.hidden = !message;
  }

  function roleLabel(role) {
    return (
      { owner: "Owner", manager: "Manager", sales_rep: "Sales rep", marketing: "Marketing" }[
        role
      ] || role
    );
  }

  function canReview() {
    const membership = (state.organizations || []).find(function (org) {
      return org.org_id === state.orgId;
    });
    return membership && (membership.role === "owner" || membership.role === "manager");
  }

  // A hosted free-tier service sleeps. Waking it can take 30+ seconds, so a
  // single failed request is not "offline" — it may be a cold start. Try a few
  // times with honest copy before giving up.
  async function callWithWakeup(method, path, body) {
    const delays = [0, 2000, 4000, 8000, 12000];
    let lastError = null;
    for (let attempt = 0; attempt < delays.length; attempt++) {
      if (delays[attempt]) await new Promise(function (r) { setTimeout(r, delays[attempt]); });
      try {
        return await net.call(method, path, body);
      } catch (error) {
        lastError = error;
        const retryable = error.code === "network_error" || error.code === "bad_response";
        if (!retryable) throw error;
        if (attempt < delays.length - 1) {
          announce(
            "Connecting to the server… the first load can take up to 30 seconds.",
            "warn"
          );
        }
      }
    }
    throw lastError;
  }

  async function refreshAll() {
    if (!net.signedIn()) {
      state.me = null;
      render();
      renderJoinCard();
      return;
    }
    // Guard against a refresh started under a previous session resolving after
    // an account switch and painting stale account data into the new session.
    const generation = ++state.sessionGeneration;
    try {
      const me = await callWithWakeup("GET", "/api/auth/me");
      if (generation !== state.sessionGeneration) return;
      state.me = me;
      setOffline(false);
      await useLocalWorkspaceFor(me.profile.user_id);
      state.organizations = me.organizations || [];
      await loadMyInvitations();
      if (!state.orgId || !state.organizations.some(function (o) { return o.org_id === state.orgId; })) {
        state.orgId = state.organizations.length ? state.organizations[0].org_id : null;
      }
      await refreshOrgData();
      if (generation !== state.sessionGeneration) {
        return;
      }
      announce("", null);
      render();
      renderJoinCard();
      if (window.ClearCommitSyncStateChanged) window.ClearCommitSyncStateChanged();
    } catch (error) {
      if (generation !== state.sessionGeneration) return;
      if (error.code === "network_error") {
        setOffline(true);
        announce("Offline: showing the last known state. Nothing new is synced.", "warn");
      } else if (error.status === 401 || error.code === "token_expired" || error.code === "invalid_token") {
        // A rejected session must fully clear account-scoped state. Leaving the
        // token in place renders a signed-out card over a dead session and the
        // next account inherits the previous account's UI.
        clearAccountState();
        announce("Your session ended. Sign in again.", "warn");
      } else {
        announce(error.message, "error");
      }
      if (generation !== state.sessionGeneration) return;
      render();
    }
  }

  // The personal workspace on this PC follows the signed-in account, so two
  // people sharing a computer never see each other's local conversations.
  // A stable hash of the user id is used - never the email or the token.
  async function useLocalWorkspaceFor(userId) {
    const key = await accountKey(userId);
    if (state.localWorkspaceKey === key) return;
    try {
      const local = localBridge();
      if (!local) return;
      // Upload an open guest conversation before the workspace changes,
      // otherwise the switch hides it and the work looks lost.
      if (state.localWorkspaceKey === null && window.ClearCommitBeforeWorkspaceSwitch) {
        await window.ClearCommitBeforeWorkspaceSwitch();
      }
      await local.call("use_workspace", { account_key: key });
      state.localWorkspaceKey = key;
      if (window.ClearCommitLocalWorkspaceChanged) window.ClearCommitLocalWorkspaceChanged();
    } catch (error) {
      announce("Could not open this account's local workspace: " + error.message, "warn");
    }
  }

  async function accountKey(userId) {
    const text = "ccw:" + String(userId || "");
    if (window.crypto && window.crypto.subtle) {
      try {
        const digest = await window.crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
        return Array.from(new Uint8Array(digest)).slice(0, 12).map(function (b) {
          return b.toString(16).padStart(2, "0");
        }).join("");
      } catch (error) {
        /* fall through to the simple hash */
      }
    }
    let hash = 5381;
    for (let i = 0; i < text.length; i++) hash = ((hash << 5) + hash + text.charCodeAt(i)) >>> 0;
    return "h" + hash.toString(16);
  }

  function clearAccountState() {
    net.setToken("");
    if (socket) {
      socket.close();
      socket = null;
    }
    state.me = null;
    state.orgId = null;
    state.organizations = [];
    state.members = [];
    state.conversations = [];
    state.myInsights = [];
    state.sharedInsights = [];
    state.playbook = [];
    state.invitations = [];
    state.lastEvent = null;
    state.liveStatus = "signed_out";
    state.sessionGeneration++;
    state.localWorkspaceKey = null;
    const local = localBridge();
    if (local) {
      // Return to the guest workspace so the next person at this computer
      // cannot see the previous account's personal conversations.
      Promise.resolve(local.call("use_workspace", { account_key: null }))
        .then(function () {
          if (window.ClearCommitLocalWorkspaceChanged) window.ClearCommitLocalWorkspaceChanged();
        })
        .catch(function () {
          /* the sign-out itself still succeeded */
        });
    }
    if (dom.root) clear(dom.root);
    renderLive();
  }

  async function refreshOrgData() {
    if (!state.orgId) {
      state.members = [];
      state.conversations = [];
      state.myInsights = [];
      state.sharedInsights = [];
      state.playbook = [];
      state.invitations = [];
      return;
    }
    const org = state.orgId;
    const [orgDetail, conversations, mine, shared, playbook] = await Promise.all([
      net.call("GET", "/api/orgs/" + org),
      net.call("GET", "/api/orgs/" + org + "/conversations"),
      net.call("GET", "/api/orgs/" + org + "/insights?scope=mine"),
      net.call("GET", "/api/orgs/" + org + "/insights?scope=shared"),
      net.call("GET", "/api/orgs/" + org + "/playbook"),
    ]);
    state.members = orgDetail.members || [];
    state.conversations = conversations.conversations || [];
    state.myInsights = mine.insights || [];
    state.sharedInsights = shared.insights || [];
    state.playbook = playbook.entries || [];
    if (canReview()) {
      try {
        const invites = await net.call("GET", "/api/orgs/" + org + "/invitations");
        state.invitations = invites.invitations || [];
      } catch (error) {
        state.invitations = [];
      }
    } else {
      state.invitations = [];
    }
  }

  async function resolveMode() {
    if (!state.mode) state.mode = (await net.authMode()) || "demo";
    return state.mode;
  }

  async function signIn(event) {
    event.preventDefault();
    const email = dom.authEmail.value.trim();
    const password = dom.authPassword.value;
    if (!email || !password) return;
    setBusy(true);
    try {
      const mode = await resolveMode();
      const data = await net.signIn(mode, { email: email, password: password });
      // A new identity invalidates anything started under the previous one.
      state.sessionGeneration++;
      state.me = null;
      state.orgId = null;
      state.organizations = [];
      state.members = [];
      state.conversations = [];
      state.myInsights = [];
      state.sharedInsights = [];
      state.playbook = [];
      state.invitations = [];
      if (socket) socket.close();
      socket = net.connect({ onEvent: onServerEvent, onStatus: onLiveStatus });
      announce(
        "Signed in as " + data.profile.display_name + " (" + mode + " authentication).",
        "ok"
      );
      await refreshAll();
    } catch (error) {
      failure(error, "Sign-in failed.");
    } finally {
      setBusy(false);
    }
  }
  async function signUp(event) {
    event.preventDefault();
    const email = dom.authEmail.value.trim();
    const name = dom.authName.value.trim();
    const password = dom.authPassword.value;
    if (!email || !name || !password) {
      announce("Email, display name, and password are required.", "error");
      return;
    }
    if (password.length < 8) {
      announce("Choose a password with at least 8 characters.", "error");
      return;
    }
    setBusy(true);
    try {
      const mode = await resolveMode();
      const data = await net.signUp(mode, { email: email, displayName: name, password: password });
      if (data.needsConfirmation) {
        announce(
          "Account created. Confirm the email Supabase sent you, then sign in.",
          "ok"
        );
        return;
      }
      if (data.mode === "supabase") {
        socket = net.connect({ onEvent: onServerEvent, onStatus: onLiveStatus });
      } else {
        socket = net.connect({ onEvent: onServerEvent, onStatus: onLiveStatus });
      }
      announce(
        data.mode === "supabase"
          ? "Account created with Supabase Auth."
          : "Account created. This is demo authentication, not a production identity.",
        "ok"
      );
      await refreshAll();
    } catch (error) {
      failure(error, "Account creation failed.");
    } finally {
      setBusy(false);
    }
  }
  function signOut() {
    clearAccountState();
    announce("Signed out. Local workspace data is untouched.", "ok");
    render();
  }

  async function joinByCode(event) {
    event.preventDefault();
    const input = document.getElementById("join-code");
    const code = (input && input.value ? input.value : "").trim();
    if (!code) return;
    setBusy(true);
    try {
      const membership = await net.call("POST", "/api/join", { code: code });
      state.orgId = membership.org_id;
      if (input) input.value = "";
      announce(
        "Joined " + (membership.organization ? membership.organization.name : "the team") +
          " as " + roleLabel(membership.role) + ".",
        "ok"
      );
      resubscribe();
      await refreshAll();
    } catch (error) {
      if (error.code === "invalid_code") {
        announce("That code was not recognised. Check it with your manager.", "error");
      } else {
        failure(error, "Could not join that team.");
      }
    } finally {
      setBusy(false);
    }
  }

  function renderJoinCard() {
    const card = document.getElementById("join-card");
    if (!card) return;
    // Visible whenever signed in. It stays available even when the account is
    // already in a company, because people belong to several teams.
    card.hidden = !net.signedIn();
    const hint = card.querySelector(".join-hint");
    if (hint) {
      hint.textContent = (state.organizations || []).length
        ? "Join another team: enter the code your manager gave you."
        : "Ask your manager for the team code, then enter it here.";
    }
  }

  async function createOrg(event) {
    event.preventDefault();
    const name = dom.orgName.value.trim();
    if (!name) return;
    setBusy(true);
    try {
      const org = await net.call("POST", "/api/orgs", { name: name });
      dom.orgName.value = "";
      state.orgId = org.org_id;
      announce("Created " + org.name + ".", "ok");
      resubscribe();
      await refreshAll();
    } catch (error) {
      failure(error, "That action failed.");
    } finally {
      setBusy(false);
    }
  }

  async function inviteMember(event) {
    event.preventDefault();
    const email = dom.inviteEmail.value.trim();
    const role = dom.inviteRole.value;
    if (!email) return;
    setBusy(true);
    try {
      await net.call("POST", "/api/orgs/" + state.orgId + "/invitations", {
        email: email,
        role: role,
      });
      dom.inviteEmail.value = "";
      announce(
        "Added " + email + ". They will see the invitation automatically after signing in with that address.",
        "ok"
      );
      await refreshOrgData();
      render();
    } catch (error) {
      failure(error, "That action failed.");
    } finally {
      setBusy(false);
    }
  }

  async function acceptInvitation(invitationId) {
    setBusy(true);
    try {
      const membership = await net.call("POST", "/api/invitations/accept", {
        invitation_id: invitationId,
      });
      state.orgId = membership.org_id;
      announce("Joined " + membership.organization.name + ".", "ok");
      resubscribe();
      await refreshAll();
    } catch (error) {
      failure(error, "That action failed.");
    } finally {
      setBusy(false);
    }
  }

  // Discover invitations addressed to the verified account email, so the
  // employee never has to copy an invitation id.
  async function loadMyInvitations() {
    try {
      const mine = await net.call("GET", "/api/invitations/mine");
      state.pendingInvitations = mine.invitations || [];
    } catch (error) {
      state.pendingInvitations = [];
    }
    return state.pendingInvitations;
  }

  async function joinInvitation(invitation) {
    setBusy(true);
    try {
      const membership = await net.call("POST", "/api/invitations/accept", {
        invitation_id: invitation.invitation_id,
      });
      state.orgId = membership.org_id;
      announce("Joined " + membership.organization.name + " as " + roleLabel(membership.role) + ".", "ok");
      resubscribe();
      await refreshAll();
    } catch (error) {
      failure(error, "Could not join that organization.");
    } finally {
      setBusy(false);
    }
  }

  async function acceptPendingMine() {
    setBusy(true);
    try {
      const mine = await net.call("GET", "/api/invitations/mine");
      const first = (mine.invitations || [])[0];
      if (!first) {
        announce("No open invitation for your email address.", "warn");
        return;
      }
      await net.call("POST", "/api/invitations/accept", { invitation_id: first.invitation_id });
      state.orgId = first.org_id;
      announce("Joined " + first.organization.name + ".", "ok");
      resubscribe();
      await refreshAll();
    } catch (error) {
      failure(error, "That action failed.");
    } finally {
      setBusy(false);
    }
  }

  async function createConversation(event) {
    event.preventDefault();
    const title = dom.convTitle.value.trim();
    if (!title || !state.orgId) return;
    setBusy(true);
    try {
      const conversation = await net.call("POST", "/api/orgs/" + state.orgId + "/conversations", {
        title: title,
      });
      const lines = dom.convLines.value
        .split("\n")
        .map(function (line) { return line.trim(); })
        .filter(Boolean)
        .map(function (line) {
          const match = line.match(/^([A-Za-z ]{2,20}):\s*(.+)$/);
          if (match) return { speaker: match[1].trim(), content: match[2].trim() };
          return { speaker: "Rep", content: line };
        });
      if (lines.length) {
        await net.call(
          "POST",
          "/api/orgs/" + state.orgId + "/conversations/" + conversation.conversation_id + "/utterances",
          { utterances: lines }
        );
      }
      dom.convTitle.value = "";
      dom.convLines.value = "";
      announce("Conversation saved to the team backend.", "ok");
      await refreshOrgData();
      render();
    } catch (error) {
      failure(error, "That action failed.");
    } finally {
      setBusy(false);
    }
  }

  async function createInsight(event) {
    event.preventDefault();
    const conversationId = dom.insightConversation.value;
    if (!conversationId || !state.orgId) return;
    setBusy(true);
    try {
      const detail = await net.call(
        "GET",
        "/api/orgs/" + state.orgId + "/conversations/" + conversationId
      );
      const lines = detail.utterances || [];
      if (!lines.length) {
        announce("That conversation has no lines yet.", "warn");
        return;
      }
      const selected = lines.slice(0, Math.min(2, lines.length));
      await net.call("POST", "/api/orgs/" + state.orgId + "/insights", {
        conversation_id: conversationId,
        title: dom.insightTitle.value.trim() || "Untitled observation",
        observed_issue: dom.insightIssue.value.trim() || "Not described yet.",
        suggested_alternative: dom.insightAlternative.value.trim() || "Not described yet.",
        evidence: selected.map(function (line) {
          return { utterance_id: line.utterance_id, quote: line.content.slice(0, 300) };
        }),
      });
      dom.insightTitle.value = "";
      dom.insightIssue.value = "";
      dom.insightAlternative.value = "";
      announce("Insight saved privately. Share it when you are ready.", "ok");
      await refreshOrgData();
      render();
    } catch (error) {
      failure(error, "That action failed.");
    } finally {
      setBusy(false);
    }
  }

  async function shareInsight(insightId) {
    setBusy(true);
    try {
      await net.call("POST", "/api/insights/" + insightId + "/share", {});
      announce("Shared with your organization.", "ok");
      await refreshOrgData();
      render();
    } catch (error) {
      failure(error, "That action failed.");
    } finally {
      setBusy(false);
    }
  }

  async function promoteInsight(insightId) {
    setBusy(true);
    try {
      const insight = await net.call("GET", "/api/insights/" + insightId);
      await net.call("POST", "/api/orgs/" + state.orgId + "/playbook", {
        insight_id: insightId,
        title: insight.title,
        scenario: insight.observed_issue,
        response: insight.suggested_alternative,
        discovery_questions: ["What is the current process today?"],
      });
      announce("Added to the review queue as a draft.", "ok");
      await refreshOrgData();
      render();
    } catch (error) {
      failure(error, "That action failed.");
    } finally {
      setBusy(false);
    }
  }

  async function approveEntry(entryId) {
    setBusy(true);
    try {
      await net.call("POST", "/api/playbook/" + entryId + "/approve", {});
      announce("Approved. The playbook is updated for the whole team.", "ok");
      await refreshOrgData();
      render();
    } catch (error) {
      failure(error, "That action failed.");
    } finally {
      setBusy(false);
    }
  }

  function onLiveStatus(status) {
    state.liveStatus = status;
    renderLive();
    // A rejected session must return to the sign-in state instead of leaving
    // the user in a dead "Session rejected" view with a token that cannot work.
    if (status === "unauthorized" && net.signedIn()) {
      net.setToken("");
      state.me = null;
      state.orgId = null;
      announce("Your session was rejected. Sign in again.", "warn");
      void refreshAll();
    }
  }

  function onServerEvent(event) {
    state.lastEvent = event;
    if (!event || !event.type) return;
    const relevant = event.org_id === state.orgId;
    if (!relevant) return;
    announce(
      "Live update: " + event.type.replace(/_/g, " ") + " — refreshing authoritative state.",
      "ok"
    );
    void refreshOrgData().then(render).catch(function () {
      announce("Live update received but the refresh failed. Retrying on next event.", "warn");
    });
  }

  function failure(error, fallback) {
    if (error && error.code === "network_error") {
      setOffline(true);
      announce(
        "The team server is unreachable. This change was NOT saved and is not synchronized.",
        "warn"
      );
      return;
    }
    announce((error && error.message) || fallback, "error");
  }

  function resubscribe() {
    if (socket) socket.reconnect();
  }

  function setBusy(value) {
    state.busy = Boolean(value);
    if (dom.root) dom.root.classList.toggle("is-busy", state.busy);
  }

  function setOffline(value) {
    state.offline = Boolean(value);
    if (dom.root) {
      dom.root.classList.toggle("is-offline", state.offline);
      dom.root.querySelectorAll("button").forEach(function (button) {
        if (button.dataset.offlineSafe === "true") return;
        if (state.offline) {
          button.disabled = true;
          button.title = "Unavailable while the team server is unreachable.";
        } else if (!state.busy) {
          button.disabled = false;
          button.title = "";
        }
      });
    }
  }

  function renderLive() {
    if (!dom.live) return;
    const labels = {
      signed_out: "Not signed in",
      online: "Live",
      reconnecting: "Reconnecting…",
      unauthorized: "Session rejected",
    };
    dom.live.textContent = labels[state.liveStatus] || state.liveStatus;
    dom.live.className = "team-live is-" + state.liveStatus;
  }

  function field(labelText, input) {
    const wrapper = el("label", "team-field");
    wrapper.append(el("span", "team-field-label", labelText));
    wrapper.append(input);
    return wrapper;
  }

  function button(label, className, onClick) {
    const node = el("button", "button " + (className || ""), label);
    node.type = "button";
    node.addEventListener("click", onClick);
    return node;
  }

  function renderAuth() {
    const card = el("div", "team-card team-auth");
    card.append(el("h3", "team-card-title", "Sign in to the team workspace"));
    card.append(
      el(
        "p",
        "team-card-note",
        "This is the networked workspace: shared insights, review, and an approved playbook across machines. " +
          "The local workspace on the left stays separate and works offline."
      )
    );

    const form = el("form", "team-form");
    dom.authEmail = el("input", "team-input");
    dom.authEmail.type = "email";
    dom.authEmail.placeholder = "you@company.com";
    dom.authEmail.autocomplete = "username";
    dom.authName = el("input", "team-input");
    dom.authName.type = "text";
    dom.authName.placeholder = "Display name (sign up)";
    dom.authPassword = el("input", "team-input");
    dom.authPassword.type = "password";
    dom.authPassword.placeholder = "Password";
    dom.authPassword.autocomplete = "current-password";

    form.append(field("Email", dom.authEmail));
    form.append(field("Display name", dom.authName));
    form.append(field("Password", dom.authPassword));

    const actions = el("div", "team-actions");
    const signInButton = el("button", "button button-primary", "Sign in");
    signInButton.type = "submit";
    const signUpButton = button("Create account", "button-quiet", function () {
      void signUp({ preventDefault: function () {} });
    });
    actions.append(signInButton, signUpButton);
    form.append(actions);
    form.addEventListener("submit", function (event) {
      void signIn(event);
    });
    card.append(form);

    // The server address is configuration, not something a normal user should
    // see or type. It is keepable behind a disclosure for self-hosting.
    const advanced = el("details", "team-advanced");
    advanced.append(el("summary", "team-advanced-summary", "Advanced: server address"));
    const serverRow = el("div", "team-server");
    dom.serverInput = el("input", "team-input");
    dom.serverInput.type = "url";
    dom.serverInput.value = net.serverUrl();
    const saveServer = button("Use this server", "button-quiet", function () {
      net.setServer(dom.serverInput.value);
      announce("Team server updated.", "ok");
    });
    serverRow.append(dom.serverInput, saveServer);
    advanced.append(serverRow);
    advanced.append(
      el("p", "team-scope-note", "Only change this if you run your own ClearCommit server.")
    );
    card.append(advanced);
    const modeNote = el(
      "p",
      "team-scope-note",
      state.mode === "supabase"
        ? "Supabase Auth is active: credentials are verified by your Supabase project."
        : "Demo mode is clearly labeled: accounts are created on this server, not by an email provider."
    );
    card.append(modeNote);
    void resolveMode().then(function (mode) {
      if (mode === "supabase") {
        modeNote.textContent = "Supabase Auth is active: credentials are verified by your Supabase project.";
      }
    });
    return card;
  }

  function renderOrgPicker() {
    const card = el("div", "team-card");
    card.append(el("h3", "team-card-title", "Organization"));
    if (!state.organizations.length) {
      card.append(
        el("p", "team-card-note", "You are not in an organization yet. Create one, or accept an invitation.")
      );
    }
    const list = el("div", "team-org-list");
    state.organizations.forEach(function (org) {
      const row = el("button", "team-org" + (org.org_id === state.orgId ? " is-active" : ""));
      row.type = "button";
      row.append(el("span", "team-org-name", org.name));
      row.append(el("span", "team-org-role", roleLabel(org.role)));
      if (org.join_code) {
        row.append(el("code", "team-code", org.join_code));
        row.title = "Share this code so a teammate can join";
      }
      row.addEventListener("click", function () {
        state.orgId = org.org_id;
        void refreshOrgData().then(render);
      });
      list.append(row);
    });
    card.append(list);

    const form = el("form", "team-form team-inline");
    dom.orgName = el("input", "team-input");
    dom.orgName.placeholder = "New organization name";
    const submit = el("button", "button button-quiet", "Create");
    submit.type = "submit";
    form.append(dom.orgName, submit);
    form.addEventListener("submit", function (event) {
      void createOrg(event);
    });
    card.append(form);

    // Invitations addressed to this account's verified email. The employee
    // does not copy an id: the server matched the invitation to the token.
    if (state.pendingInvitations && state.pendingInvitations.length) {
      card.append(el("p", "team-card-note", "You have been invited to join:"));
      const invites = el("div", "team-list");
      state.pendingInvitations.forEach(function (invitation) {
        const row = el("div", "team-row is-draft");
        row.append(
          el("span", "team-row-title", invitation.organization ? invitation.organization.name : "An organization")
        );
        row.append(el("span", "team-row-meta", "Role: " + roleLabel(invitation.role)));
        row.append(button("Join", "button-primary", function () {
          void joinInvitation(invitation);
        }));
        invites.append(row);
      });
      card.append(invites);
    } else if (!state.organizations.length) {
      card.append(
        el(
          "p",
          "team-scope-note",
          "Ask a manager to add this email address, then refresh. Invitations appear here automatically."
        )
      );
    }
    return card;
  }

  // Calls grouped by the person who owns them. Facts only: how many calls,
  // how many lines, whether each is shared. No scores, no rankings.
  function callsByOwner() {
    const groups = new Map();
    state.conversations.forEach(function (conversation) {
      const key = conversation.owner_id || "unknown";
      if (!groups.has(key)) {
        groups.set(key, {
          ownerId: key,
          name: conversation.owner_name || (conversation.is_mine ? "You" : "Teammate"),
          isMine: Boolean(conversation.is_mine),
          conversations: [],
        });
      }
      groups.get(key).conversations.push(conversation);
    });
    return Array.from(groups.values()).sort(function (a, b) {
      return b.conversations.length - a.conversations.length;
    });
  }

  // A manager works across the team; an employee works on their own calls.
  // Same data, different scope, decided by the role the server reported.
  function renderCallsList(conversations, emptyText) {
    if (!conversations.length) return el("p", "team-card-note", emptyText);
    const list = el("div", "team-list");
    conversations.forEach(function (conversation) {
      const row = el("div", "team-row");
      row.append(el("span", "team-row-title", conversation.title));
      row.append(
        el(
          "span",
          "team-row-meta",
          (conversation.line_count || 0) + " lines · " +
            (conversation.visibility === "shared" ? "shared with team" : "private")
        )
      );
      list.append(row);
    });
    return list;
  }

  function renderCallsTab() {
    const reviewer = canReview();
    const mine = state.conversations.filter(function (c) { return c.is_mine; });
    const others = state.conversations.filter(function (c) { return !c.is_mine; });

    const card = el("div", "team-card team-calls");
    const head = el("div", "calls-head");
    head.append(
      el("h3", "team-card-title", reviewer ? "Team calls" : "My calls")
    );
    const total = reviewer ? state.conversations.length : mine.length;
    head.append(el("span", "calls-total", total + (total === 1 ? " call" : " calls")));
    card.append(head);
    card.append(
      el(
        "p",
        "team-card-note",
        reviewer
          ? "Calls shared by the team. Private calls stay private until their owner shares them."
          : "Your calls. They stay private until you share one with the team."
      )
    );

    if (!reviewer) {
      // An employee cares about their own work, not a roster.
      card.append(renderCallsList(mine, "You have no calls yet."));
      return card;
    }

    const groups = callsByOwner();
    if (!groups.length) {
      card.append(el("p", "team-card-note", "No calls in this organization yet."));
      return card;
    }
    if (!others.length) {
      card.append(
        el("p", "team-card-note", "No teammate has shared a call with the team yet.")
      );
    }

    groups.forEach(function (group) {
      const block = el("div", "calls-group");
      const header = el("div", "calls-group-head");
      const who = el("div", "calls-who");
      who.append(el("span", "profile-avatar is-small", initials(group.name)));
      const label = el("div", "calls-who-copy");
      label.append(el("span", "calls-name", group.name + (group.isMine ? " (you)" : "")));
      const shared = group.conversations.filter(function (c) { return c.visibility === "shared"; }).length;
      const lines = group.conversations.reduce(function (sum, c) { return sum + (c.line_count || 0); }, 0);
      label.append(
        el(
          "span",
          "calls-summary",
          group.conversations.length + (group.conversations.length === 1 ? " call" : " calls") +
            " · " + lines + " lines · " + shared + " shared"
        )
      );
      who.append(label);
      header.append(who);
      block.append(header);

      const rows = el("div", "team-list");
      group.conversations.forEach(function (conversation) {
        const row = el("div", "team-row");
        row.append(el("span", "team-row-title", conversation.title));
        row.append(
          el(
            "span",
            "team-row-meta",
            (conversation.line_count || 0) + " lines · " +
              (conversation.visibility === "shared" ? "shared with team" : "private")
          )
        );
        rows.append(row);
      });
      block.append(rows);
      card.append(block);
    });

    return card;
  }

  function renderConversations() {
    const card = el("div", "team-card");
    card.append(el("h3", "team-card-title", "New conversation"));
    const form = el("form", "team-form");
    dom.convTitle = el("input", "team-input");
    dom.convTitle.placeholder = "Conversation title";
    dom.convLines = el("textarea", "team-textarea");
    dom.convLines.rows = 4;
    dom.convLines.placeholder = "Rep: line one\nCustomer: line two";
    const submit = el("button", "button button-primary", "Save conversation");
    submit.type = "submit";
    form.append(field("Title", dom.convTitle), field("Lines", dom.convLines), submit);
    form.addEventListener("submit", function (event) {
      void createConversation(event);
    });
    card.append(form);
    return card;
  }
  function renderInsights() {
    const card = el("div", "team-card");
    card.append(el("h3", "team-card-title", "Your insights"));
    if (!state.myInsights.length) {
      card.append(el("p", "team-card-note", "No private insights yet. Create one below."));
    }
    const list = el("div", "team-list");
    state.myInsights.forEach(function (insight) {
      const row = el("div", "team-row");
      row.append(el("span", "team-row-title", insight.title));
      row.append(el("span", "team-row-meta", insight.visibility === "shared" ? "Shared with team" : "Private"));
      const actions = el("div", "team-row-actions");
      if (insight.visibility !== "shared") {
        actions.append(button("Share with team", "button-quiet", function () {
          void shareInsight(insight.insight_id);
        }));
        actions.append(button("Draft playbook entry", "button-quiet", function () {
          void promoteInsight(insight.insight_id);
        }));
      }
      row.append(actions);
      list.append(row);
    });
    card.append(list);

    const form = el("form", "team-form");
    dom.insightConversation = el("select", "team-input");
    state.conversations.forEach(function (conversation) {
      const option = el("option", null, conversation.title);
      option.value = conversation.conversation_id;
      dom.insightConversation.append(option);
    });
    dom.insightTitle = el("input", "team-input");
    dom.insightTitle.placeholder = "Observation title";
    dom.insightIssue = el("textarea", "team-textarea");
    dom.insightIssue.rows = 2;
    dom.insightIssue.placeholder = "What was observed (cite the lines)";
    dom.insightAlternative = el("textarea", "team-textarea");
    dom.insightAlternative.rows = 2;
    dom.insightAlternative.placeholder = "Suggested alternative";
    const submit = el("button", "button button-primary", "Save private insight");
    submit.type = "submit";
    form.append(
      field("Conversation", dom.insightConversation),
      field("Title", dom.insightTitle),
      field("Observed issue", dom.insightIssue),
      field("Suggested alternative", dom.insightAlternative),
      submit
    );
    form.addEventListener("submit", function (event) {
      void createInsight(event);
    });
    card.append(form);
    card.append(
      el("p", "team-scope-note", "Evidence lines are attached automatically from the conversation you pick.")
    );
    return card;
  }

  const COMMITMENT_STATUS = {
    awaiting_confirmation: "Needs confirmation",
    open: "Open",
    blocked: "Blocked",
    done: "Done",
    cancelled: "Cancelled",
  };

  function commitmentRow(commitment) {
    const row = el("div", "commit-row is-" + commitment.status);
    const main = el("div", "commit-main");
    main.append(el("span", "commit-title", commitment.title));

    const meta = el("span", "commit-meta");
    meta.append(el("span", "commit-owner", commitment.owner_name || "Unassigned"));
    if (commitment.due_on) {
      meta.append(el("span", "commit-due", "due " + commitment.due_on));
    } else {
      meta.append(el("span", "commit-due is-missing", "no date"));
    }
    main.append(meta);

    if (commitment.evidence_quote) {
      main.append(el("q", "commit-evidence", commitment.evidence_quote));
    }

    row.append(main);
    row.append(
      el(
        "span",
        "commit-status is-" + commitment.status,
        COMMITMENT_STATUS[commitment.status] || commitment.status
      )
    );

    const actions = el("div", "commit-actions");
    if (commitment.status === "awaiting_confirmation") {
      actions.append(button("Confirm", "button-quiet", function () {
        void updateCommitment(commitment, {
          due_on: commitment.due_on || new Date().toISOString().slice(0, 10),
        });
      }));
    }
    if (commitment.status === "open" || commitment.status === "awaiting_confirmation") {
      actions.append(button("Blocked", "button-quiet", function () {
        void updateCommitment(commitment, { status: "blocked" });
      }));
    }
    if (commitment.status !== "done" && commitment.status !== "cancelled") {
      actions.append(button("Done", "button-primary", function () {
        void updateCommitment(commitment, { status: "done" });
      }));
    }
    if (actions.childNodes.length) row.append(actions);
    return row;
  }

  async function updateCommitment(commitment, changes) {
    try {
      await net.call("PATCH", "/api/commitments/" + commitment.commitment_id, changes);
      await refreshCommitments();
      render();
    } catch (error) {
      failure(error, "Could not update that commitment.");
    }
  }

  async function refreshCommitments() {
    if (!state.orgId) {
      state.commitmentsMine = [];
      state.commitmentsTeam = [];
      return;
    }
    try {
      const mine = await net.call("GET", "/api/orgs/" + state.orgId + "/commitments?scope=mine");
      state.commitmentsMine = mine.commitments || [];
      const team = await net.call("GET", "/api/orgs/" + state.orgId + "/commitments?scope=team");
      state.commitmentsTeam = team.commitments || [];
    } catch (error) {
      state.commitmentsMine = [];
      state.commitmentsTeam = [];
    }
  }

  function renderCommitmentsTab() {
    const reviewer = canReview();
    const mine = state.commitmentsMine || [];
    const team = state.commitmentsTeam || [];
    const openMine = mine.filter(function (c) {
      return c.status !== "done" && c.status !== "cancelled";
    }).length;
    const blocked = team.filter(function (c) { return c.status === "blocked"; }).length;

    const card = el("div", "team-card team-commits");
    const head = el("div", "calls-head");
    head.append(el("h3", "team-card-title", reviewer ? "Team commitments" : "My commitments"));
    head.append(el("span", "calls-total", openMine + " open"));
    card.append(head);
    card.append(
      el(
        "p",
        "team-card-note",
        "A promise is only a commitment once a person confirms the owner and the date. Status changes are audited."
      )
    );
    if (blocked) {
      card.append(el("p", "commit-blocked-note", blocked + " blocked and need attention."));
    }

    // What you own always comes first.
    const mineList = el("div", "commit-list");
    if (!openMine && !mine.length) {
      card.append(el("p", "team-card-note", "You have no commitments yet."));
    } else {
      mine.forEach(function (commitment) { mineList.append(commitmentRow(commitment)); });
      card.append(mineList);
    }

    if (reviewer && team.length) {
      const others = team.filter(function (c) {
        return c.owner_id !== (state.me && state.me.profile && state.me.profile.user_id);
      });
      if (others.length) {
        card.append(el("h4", "commit-subhead", "Across the team"));
        const list = el("div", "commit-list");
        others.forEach(function (commitment) { list.append(commitmentRow(commitment)); });
        card.append(list);
      }
    }

    const form = el("form", "team-form");
    dom.commitTitle = el("input", "team-input");
    dom.commitTitle.placeholder = "What did someone promise?";
    dom.commitDue = el("input", "team-input");
    dom.commitDue.type = "date";
    dom.commitOwner = el("select", "team-input");
    const meId = state.me && state.me.profile && state.me.profile.user_id;
    (state.members || []).forEach(function (member) {
      const option = el("option", null, (member.profile && member.profile.display_name) || member.user_id);
      option.value = member.user_id;
      dom.commitOwner.append(option);
    });
    if (meId) dom.commitOwner.value = meId;
    const submit = el("button", "button button-primary", "Add commitment");
    submit.type = "submit";
    form.append(
      field("Promise", dom.commitTitle),
      field("Owner", dom.commitOwner),
      field("Due date", dom.commitDue),
      submit
    );
    form.addEventListener("submit", function (event) {
      void createCommitment(event);
    });
    card.append(form);
    return card;
  }

  async function createCommitment(event) {
    event.preventDefault();
    if (!state.orgId) return;
    const title = (dom.commitTitle.value || "").trim();
    if (!title) {
      announce("Give the commitment a title.", "error");
      return;
    }
    setBusy(true);
    try {
      await net.call("POST", "/api/orgs/" + state.orgId + "/commitments", {
        title: title,
        owner_id: dom.commitOwner.value || null,
        due_on: dom.commitDue.value || null,
      });
      dom.commitTitle.value = "";
      dom.commitDue.value = "";
      announce("Commitment added. Confirm it once the owner and date are agreed.", "ok");
      await refreshCommitments();
      render();
    } catch (error) {
      failure(error, "Could not add that commitment.");
    } finally {
      setBusy(false);
    }
  }

  function renderPlaybook() {
    const card = el("div", "team-card");
    card.append(el("h3", "team-card-title", "Shared playbook"));
    const drafts = state.playbook.filter(function (entry) { return entry.status === "draft"; });
    const approved = state.playbook.filter(function (entry) { return entry.status === "approved"; });
    card.append(el("p", "team-card-note", drafts.length + " awaiting review · " + approved.length + " approved"));
    const list = el("div", "team-list");
    state.playbook.forEach(function (entry) {
      const row = el("div", "team-row is-" + entry.status);
      row.append(el("span", "team-row-title", entry.title));
      row.append(
        el(
          "span",
          "team-row-meta",
          entry.status === "approved"
            ? "Approved by " + (entry.approved_by_name || "a reviewer") + " · v" + entry.version
            : "Draft by " + (entry.author_name || "a teammate")
        )
      );
      if (entry.status === "draft" && canReview()) {
        row.append(button("Approve", "button-primary", function () {
          void approveEntry(entry.entry_id);
        }));
      }
      list.append(row);
    });
    card.append(list);
    return card;
  }

  // A manager opening one teammate: what that person has shared, and their
  // evidence-linked observations. Facts about shared work only.
  async function openMember(member) {
    state.memberView = member.user_id;
    render();
  }

  function renderMemberDetail() {
    const member = (state.members || []).find(function (m) {
      return m.user_id === state.memberView;
    });
    if (!member) {
      state.memberView = null;
      return null;
    }
    const name = (member.profile && member.profile.display_name) || member.user_id;
    const card = el("div", "team-card");
    const head = el("div", "calls-head");
    head.append(el("h3", "team-card-title", name));
    head.append(button("Back", "button-quiet", function () {
      state.memberView = null;
      render();
    }));
    card.append(head);
    card.append(el("p", "team-card-note", roleLabel(member.role) + " · " + ((member.profile && member.profile.email) || "")));

    const calls = state.conversations.filter(function (c) {
      return c.owner_id === member.user_id;
    });
    const insights = (state.sharedInsights || []).filter(function (i) {
      return i.owner_id === member.user_id;
    });

    const stats = el("div", "team-stats");
    function stat(value, label) {
      const box = el("div", "team-stat");
      box.append(el("span", "team-stat-value", String(value)));
      box.append(el("span", "team-stat-label", label));
      return box;
    }
    stats.append(
      stat(calls.length, calls.length === 1 ? "shared call" : "shared calls"),
      stat(insights.length, insights.length === 1 ? "shared insight" : "shared insights")
    );
    card.append(stats);

    if (calls.length) {
      const list = el("div", "team-list");
      calls.forEach(function (c) {
        const row = el("div", "team-row");
        row.append(el("span", "team-row-title", c.title));
        row.append(el("span", "team-row-meta", (c.line_count || 0) + " lines · shared"));
        list.append(row);
      });
      card.append(list);
    }
    if (insights.length) {
      const list = el("div", "team-list");
      insights.forEach(function (i) {
        const row = el("div", "team-row");
        row.append(el("span", "team-row-title", i.title));
        row.append(el("span", "team-row-meta", i.category || "observation"));
        list.append(row);
      });
      card.append(list);
    }
    card.append(
      el(
        "p",
        "team-scope-note",
        "Only work " + name + " chose to share appears here. Private calls and coaching stay private."
      )
    );
    return card;
  }
  function renderTeam() {
    const card = el("div", "team-card");
    card.append(el("h3", "team-card-title", "Members"));
    const list = el("div", "team-list");
    state.members.forEach(function (member) {
      const row = el("div", "team-row");
      row.append(el("span", "team-row-title", (member.profile && member.profile.display_name) || member.user_id));
      row.append(el("span", "team-row-meta", roleLabel(member.role) + " · " + (member.profile && member.profile.email)));
      list.append(row);
    });
    card.append(list);

    if (canReview()) {
      const form = el("form", "team-form team-inline");
      dom.inviteEmail = el("input", "team-input");
      dom.inviteEmail.type = "email";
      dom.inviteEmail.placeholder = "teammate@company.com";
      dom.inviteRole = el("select", "team-input");
      ["manager", "sales_rep", "marketing"].forEach(function (role) {
        const option = el("option", null, roleLabel(role));
        option.value = role;
        dom.inviteRole.append(option);
      });
      const submit = el("button", "button button-quiet", "Add employee");
      submit.type = "submit";
      form.append(dom.inviteEmail, dom.inviteRole, submit);
      form.addEventListener("submit", function (event) {
        void inviteMember(event);
      });
      card.append(form);
      if (state.invitations.length) {
        const invites = el("div", "team-list");
        state.invitations.forEach(function (invitation) {
          const row = el("div", "team-row");
          row.append(el("span", "team-row-title", invitation.email));
          row.append(el("span", "team-row-meta", "Pending · " + roleLabel(invitation.role)));
          row.append(el("code", "team-code", invitation.invitation_id));
          invites.append(row);
        });
        card.append(invites);
      }
      card.append(
        el("p", "team-scope-note", "They join by signing in with this email. No message is sent and no code needs sharing.")
      );
    }
    return card;
  }

  function renderOverview() {
    const card = el("div", "team-card team-overview");
    card.append(el("h3", "team-card-title", "Overview"));
    card.append(
      el(
        "p",
        "team-card-note",
        canReview()
          ? "What your team has shared, and what is waiting on a decision."
          : "What you have shared with the team."
      )
    );

    const drafts = state.playbook.filter(function (entry) { return entry.status === "draft"; });
    const approved = state.playbook.filter(function (entry) { return entry.status === "approved"; });
    const myShared = state.myInsights.filter(function (i) { return i.visibility === "shared"; });

    const stats = el("div", "team-stats");
    function stat(value, label, tone) {
      const box = el("div", "team-stat" + (tone ? " is-" + tone : ""));
      box.append(el("span", "team-stat-value", String(value)));
      box.append(el("span", "team-stat-label", label));
      return box;
    }
    stats.append(stat(state.members.length, state.members.length === 1 ? "member" : "members"));
    stats.append(stat(state.sharedInsights.length, "shared insights"));
    stats.append(stat(drafts.length, "awaiting review", drafts.length ? "attention" : null));
    stats.append(stat(approved.length, "approved guidance"));
    card.append(stats);

    if (canReview() && drafts.length) {
      const list = el("div", "team-list team-overview-list");
      drafts.slice(0, 4).forEach(function (entry) {
        const row = el("div", "team-row is-draft");
        row.append(el("span", "team-row-title", entry.title));
        row.append(el("span", "team-row-meta", "Draft by " + (entry.author_name || "a teammate")));
        row.append(button("Approve", "button-primary", function () {
          void approveEntry(entry.entry_id);
        }));
        list.append(row);
      });
      card.append(list);
      if (drafts.length > 4) {
        card.append(el("p", "team-scope-note", (drafts.length - 4) + " more draft entries below."));
      }
    } else if (canReview()) {
      card.append(el("p", "team-scope-note", "No entries are waiting for review."));
    } else if (myShared.length) {
      card.append(
        el("p", "team-scope-note",
          myShared.length + (myShared.length === 1 ? " insight is" : " insights are") + " visible to your team.")
      );
    } else {
      card.append(
        el("p", "team-scope-note", "You have not shared any insights yet. Sharing is always your choice.")
      );
    }

    if (!state.members.length) {
      card.append(el("p", "team-scope-note", "Select an organization to see its team."));
    }
    return card;
  }

  function activeOrg() {
    return (state.organizations || []).find(function (o) {
      return o.org_id === state.orgId;
    }) || null;
  }

  function initials(text) {
    return String(text || "?")
      .split(/[\s@._-]+/)
      .filter(Boolean)
      .slice(0, 2)
      .map(function (part) { return part[0].toUpperCase(); })
      .join("");
  }

  // A real profile bar: who you are, which company you are acting in, and your
  // role there. Without it the page reads as cards with no owner.
  function renderProfileBar() {
    const bar = el("div", "profile-bar");
    const profile = (state.me && state.me.profile) || {};
    const org = activeOrg();

    const identity = el("div", "profile-identity");
    identity.append(el("span", "profile-avatar", initials(profile.display_name)));
    const names = el("div", "profile-names");
    names.append(el("span", "profile-name", profile.display_name || "Signed in"));
    names.append(el("span", "profile-mail", profile.email || ""));
    identity.append(names);

    const context = el("div", "profile-context");
    if (org) {
      context.append(el("span", "profile-org", org.name));
      context.append(el("span", "profile-role is-" + org.role, roleLabel(org.role)));
      if (org.join_code) {
        const code = el("code", "profile-code", org.join_code);
        code.title = "Share this code to invite a teammate";
        context.append(code);
      }
    } else {
      context.append(el("span", "profile-org is-empty", "No company yet"));
    }

    const actions = el("div", "profile-actions");
    actions.append(button("Refresh", "button-quiet", function () { void refreshAll(); }));
    actions.append(button("Sign out", "button-quiet", signOut));

    bar.append(identity, context, actions);
    return bar;
  }

  // Sections rather than one flat grid: identity, then what needs attention,
  // then the team's material. Each block has its own heading so the page has
  // a hierarchy instead of a single column of cards.
  function section(title, note, cards) {
    const wrap = el("section", "team-section");
    const head = el("div", "team-section-head");
    const titles = el("div", "team-section-titles");
    titles.append(el("h2", "team-section-title", title));
    if (note) titles.append(el("p", "team-section-note", note));
    head.append(titles);
    wrap.append(head);
    const body = el("div", "team-section-body");
    cards.forEach(function (card) { if (card) body.append(card); });
    wrap.append(body);
    return wrap;
  }

  // Tabs, not one long scroll: each area of the product gets its own view.
  const TEAM_TABS = [
    { id: "overview", label: "Overview" },
    { id: "calls", label: "Calls" },
    { id: "insights", label: "Insights" },
    { id: "commitments", label: "Commitments" },
    { id: "playbook", label: "Playbook" },
    { id: "team", label: "Team" },
    { id: "settings", label: "Settings" },
  ];

  function setTab(id) {
    state.tab = id;
    render();
  }

  function renderTabs() {
    const nav = el("nav", "team-tabs");
    nav.setAttribute("role", "tablist");
    TEAM_TABS.forEach(function (tab) {
      const active = (state.tab || "overview") === tab.id;
      const button = el("button", "team-tab" + (active ? " is-active" : ""), tab.label);
      button.type = "button";
      button.setAttribute("role", "tab");
      button.setAttribute("aria-selected", active ? "true" : "false");
      if (tab.id === "playbook") {
        const drafts = (state.playbook || []).filter(function (e) { return e.status === "draft"; }).length;
        if (drafts) button.append(el("span", "team-tab-badge", String(drafts)));
      }
      button.addEventListener("click", function () { setTab(tab.id); });
      nav.append(button);
    });
    return nav;
  }

  function renderTabBody() {
    const tab = state.tab || "overview";
    const wrap = el("div", "team-panel");
    wrap.setAttribute("role", "tabpanel");
    if (tab === "overview") {
      wrap.append(renderOverview(), renderOrgPicker());
    } else if (tab === "calls") {
      wrap.append(renderCallsTab(), renderConversations());
    } else if (tab === "insights") {
      wrap.append(renderInsights());
    } else if (tab === "commitments") {
      wrap.append(renderCommitmentsTab());
    } else if (tab === "playbook") {
      wrap.append(renderPlaybook());
    } else if (tab === "team") {
      const detail = renderMemberDetail();
      wrap.append(detail || renderTeam());
    } else {
      wrap.append(renderOrgPicker(), renderTeam());
    }
    return wrap;
  }

  function renderSignedIn() {
    const parts = [renderProfileBar()];
    if (!state.organizations.length) {
      parts.push(
        section(
          "Get started",
          "Create a company, or join one with the code your manager gave you.",
          [renderOrgPicker()]
        )
      );
      return parts;
    }
    parts.push(renderTabs());
    const org = activeOrg();
    parts.push(
      section(
        (TEAM_TABS.find(function (t) { return t.id === (state.tab || "overview"); }) || {}).label || "Overview",
        org ? org.name : null,
        [renderTabBody()]
      )
    );
    return parts;
  }
  function render() {
    if (!dom.root) return;
    clear(dom.root);
    renderLive();
    if (!net.signedIn() || !state.me) {
      dom.root.append(renderAuth());
    } else {
      renderSignedIn().forEach(function (node) {
        dom.root.append(node);
      });
    }
    if (state.offline) setOffline(true);
    renderJoinCard();
  }

  function init() {
    // Start waking a sleeping hosted backend immediately, before the user
    // reaches the sign-in form.
    if (window.ClearCommitNet) void window.ClearCommitNet.health();
    const joinForm = document.getElementById("join-form");
    if (joinForm) joinForm.addEventListener("submit", function (e) { void joinByCode(e); });
    dom.root = document.getElementById("team-root");
    dom.notice = document.getElementById("team-notice");
    dom.live = document.getElementById("team-live");
    if (!dom.root) return;
    if (net.signedIn()) {
      socket = net.connect({ onEvent: onServerEvent, onStatus: onLiveStatus });
    }
    render();
    void refreshAll();
  }

  window.ClearCommitTeamView = {
    init: init,
    refresh: refreshAll,
    // The desktop needs to know which company to save a conversation into.
    activeOrgId: function () {
      return state.orgId || null;
    },
    __debug: function () {
      return {
        me: state.me ? state.me.profile.email : null,
        orgId: state.orgId,
        orgs: state.organizations.length,
        generation: state.sessionGeneration,
        signedIn: net.signedIn(),
        header: Boolean(dom.root && dom.root.querySelector(".team-header")),
      };
    },
    isSignedIn: function () {
      return net.signedIn();
    },
  };

  init();
})();
