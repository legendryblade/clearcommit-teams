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

    const serverRow = el("div", "team-server");
    serverRow.append(el("span", "team-field-label", "Team server"));
    dom.serverInput = el("input", "team-input");
    dom.serverInput.type = "url";
    dom.serverInput.value = net.serverUrl();
    const saveServer = button("Use this server", "button-quiet", function () {
      net.setServer(dom.serverInput.value);
      announce("Team server set to " + net.serverUrl() + ".", "ok");
    });
    serverRow.append(dom.serverInput, saveServer);
    card.append(serverRow);
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

  function renderConversations() {
    const card = el("div", "team-card");
    card.append(el("h3", "team-card-title", "Conversations (private until shared)"));
    if (!state.conversations.length) {
      card.append(el("p", "team-card-note", "No conversations in this organization yet."));
    }
    const list = el("div", "team-list");
    state.conversations.forEach(function (conversation) {
      const row = el("div", "team-row");
      row.append(el("span", "team-row-title", conversation.title));
      row.append(
        el(
          "span",
          "team-row-meta",
          (conversation.line_count || 0) + " lines · " + (conversation.is_mine ? "yours" : "shared by " + (conversation.owner_name || "teammate"))
        )
      );
      list.append(row);
    });
    card.append(list);

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

  function renderSignedIn() {
    const header = el("div", "team-header");
    const who = el("div", "team-who");
    who.append(el("span", "team-who-name", (state.me && state.me.profile.display_name) || "Signed in"));
    who.append(el("span", "team-who-mail", (state.me && state.me.profile.email) || ""));
    header.append(who);
    header.append(button("Sign out", "button-quiet", signOut));
    header.append(button("Refresh", "button-quiet", function () {
      void refreshAll();
    }));

    const grid = el("div", "team-grid");
    grid.append(
      renderOverview(),
      renderOrgPicker(),
      renderConversations(),
      renderInsights(),
      renderPlaybook(),
      renderTeam()
    );
    return [header, grid];
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
  }

  function init() {
    // Start waking a sleeping hosted backend immediately, before the user
    // reaches the sign-in form.
    if (window.ClearCommitNet) void window.ClearCommitNet.health();
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
