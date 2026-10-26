(function () {
  "use strict";

  const bridge = window.ClearCommitBridge.createBridge();

  const TYPE_LABELS = Object.freeze({
    objection: "Objection",
    unanswered_question: "Unanswered question",
    ambiguity: "Ambiguity",
    discovery: "Discovery",
    next_step: "Next step",
  });

  const ERROR_TITLES = Object.freeze({
    validation_error: "Check the input",
    not_found: "Not found",
    conflict: "Already updated",
    insufficient_evidence: "More evidence needed",
    provider_not_configured: "Provider not configured",
    provider_timeout: "Provider timed out",
    provider_auth: "Provider rejected the key",
    provider_rate_limit: "Provider rate limit",
    provider_unavailable: "Provider unavailable",
    provider_error: "Provider error",
    invalid_model_output: "Provider answer rejected",
    bridge_not_ready: "Desktop bridge not ready",
    bridge_timeout: "The app took too long",
    bridge_protocol: "Bridge response error",
    network_error: "Local server unreachable",
    unknown_method: "Action unavailable",
  });

  const DEFAULT_LIMITS = Object.freeze({
    max_evidence: 12,
    max_assistant_evidence: 6,
    max_insights: 8,
  });

  const state = {
    sessions: [],
    session: null,
    utterances: [],
    assistantNotes: [],
    insights: [],
    insightFilter: "all",
    selectedInsightId: null,
    selection: new Set(),
    playbook: [],
    playbookFilter: "all",
    selectedPlaybookId: null,
    playbookEntry: null,
    settings: null,
    provider: null,
    preview: null,
    limits: Object.assign({}, DEFAULT_LIMITS),
    lastRun: null,
    view: "desk",
    sessionFilter: "",
    busy: false,
    booted: false,
    mode: null,
  };

  const ui = {};
  const UI_IDS = {
    bootScreen: "boot-screen",
    bootMessage: "boot-message",
    bootRetry: "boot-retry",
    appShell: "app",
    providerChip: "provider-chip",
    providerDot: "provider-dot",
    providerLabel: "provider-label",
    providerDetail: "provider-detail",
    coachNavCount: "coach-nav-count",
    playbookNavCount: "playbook-nav-count",
    sessionFilter: "session-filter",
    sessionList: "session-list",
    railBuild: "rail-build",
    globalAlert: "global-alert",
    main: "main",
    deskDate: "desk-date",
    deskTitle: "desk-title",
    deskSubtitle: "desk-subtitle",
    deskMeta: "desk-meta",
    importButton: "import-button",
    addLineButton: "add-line-button",
    syncButton: "sync-button",
    syncButtonLabel: "sync-button-label",
    transcriptList: "transcript-list",
    transcriptEmpty: "transcript-empty",
    selectionCount: "selection-count",
    selectAllButton: "select-all-button",
    clearSelectionButton: "clear-selection-button",
    quotaLabel: "quota-label",
    selectionRefs: "selection-refs",
    analyzeButton: "analyze-button",
    selectionNote: "selection-note",
    deskAnalysisError: "desk-analysis-error",
    briefCard: "brief-card",
    briefProvider: "brief-provider",
    briefSummary: "brief-summary",
    briefCount: "brief-count",
    assistantLimit: "assistant-limit",
    askForm: "ask-form",
    askQuestion: "ask-question",
    askButton: "ask-button",
    assistantNotes: "assistant-notes",
    coachContext: "coach-context",
    coachTitle: "coach-title",
    coachMeta: "coach-meta",
    coachSummary: "coach-summary",
    coachSummaryText: "coach-summary-text",
    coachProvider: "coach-provider",
    coachLimitations: "coach-limitations",
    coachGrid: "coach-grid",
    insightCountLabel: "insight-count-label",
    insightFilters: "insight-filters",
    insightList: "insight-list",
    insightDetail: "insight-detail",
    coachEmpty: "coach-empty",
    playbookTitle: "playbook-title",
    playbookCountLabel: "playbook-count-label",
    playbookList: "playbook-list",
    playbookEmpty: "playbook-empty",
    playbookForm: "playbook-form",
    pbEyebrow: "pb-eyebrow",
    pbHeading: "pb-heading",
    pbStatus: "pb-status",
    pbUpdated: "pb-updated",
    pbTitle: "pb-title",
    pbScenario: "pb-scenario",
    pbCategory: "pb-category",
    pbObjection: "pb-objection",
    pbResponse: "pb-response",
    pbQuestions: "pb-questions",
    pbEvidenceRefs: "pb-evidence-refs",
    pbEvidenceSummary: "pb-evidence-summary",
    pbGateNote: "pb-gate-note",
    pbReviewer: "pb-reviewer",
    pbNote: "pb-note",
    pbSaveHint: "pb-save-hint",
    pbReset: "pb-reset",
    pbSave: "pb-save",
    pbApprove: "pb-approve",
    pbError: "pb-error",
    pbReviews: "pb-reviews",
    signalApproved: "signal-approved",
    signalDrafts: "signal-drafts",
    signalSessions: "signal-sessions",
    signalUtterances: "signal-utterances",
    signalCoverage: "signal-coverage",
    signalInsights: "signal-insights",
    signalCategories: "signal-categories",
    signalMix: "signal-mix",
    consentNote: "consent-note",
    statusDataDir: "status-data-dir",
    settingsDialog: "settings-dialog",
    settingsForm: "settings-form",
    settingsBaseUrl: "settings-base-url",
    settingsModel: "settings-model",
    settingsTimeout: "settings-timeout",
    settingsReviewer: "settings-reviewer",
    settingsStatus: "settings-status",
    settingsError: "settings-error",
    testProvider: "test-provider",
    newSessionDialog: "new-session-dialog",
    newSessionForm: "new-session-form",
    newTitle: "new-title",
    newCustomer: "new-customer",
    newCompany: "new-company",
    newRep: "new-rep",
    newDate: "new-date",
    newCustomerLanguage: "new-customer-language",
    newRepLanguage: "new-rep-language",
    newSessionError: "new-session-error",
    importDialog: "import-dialog",
    importForm: "import-form",
    importText: "import-text",
    importError: "import-error",
    addLineDialog: "add-line-dialog",
    addLineForm: "add-line-form",
    lineSpeaker: "line-speaker",
    lineTime: "line-time",
    lineOriginal: "line-original",
    lineTranslation: "line-translation",
    lineLanguage: "line-language",
    addLineError: "add-line-error",
    toastRegion: "toast-region",
    viewDesk: "view-desk",
    viewCoach: "view-coach",
    viewPlaybook: "view-playbook",
    viewSignals: "view-signals",
    viewTeam: "view-team",
    signalsTitle: "signals-title",
    teamTitle: "team-title",
    modeChip: "mode-chip",
  };

  Object.keys(UI_IDS).forEach(function (key) {
    ui[key] = document.getElementById(UI_IDS[key]);
  });

  const VIEW_ELEMENTS = {
    desk: ui.viewDesk,
    coach: ui.viewCoach,
    playbook: ui.viewPlaybook,
    signals: ui.viewSignals,
    team: ui.viewTeam,
  };

  const VIEW_TITLES = {
    desk: ui.deskTitle,
    coach: ui.coachTitle,
    playbook: ui.playbookTitle,
    signals: ui.signalsTitle,
    team: ui.teamTitle,
  };

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function clear(node) {
    if (!node) return;
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function plural(count, one, many) {
    return count + " " + (Number(count) === 1 ? one : many);
  }

  function formatDate(value) {
    if (!value) return "Undated";
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value));
    if (!match) return String(value);
    const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  }

  function formatStamp(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function formatDuration(ms) {
    const value = Number(ms) || 0;
    if (value < 1000) return value + " ms";
    return (value / 1000).toFixed(1) + " s";
  }

  function speakerLabel(speaker) {
    return speaker === "rep" ? "Representative" : "Customer";
  }

  function todayIso() {
    const now = new Date();
    const month = String(now.getMonth() + 1).padStart(2, "0");
    const day = String(now.getDate()).padStart(2, "0");
    return now.getFullYear() + "-" + month + "-" + day;
  }

  function errorTitle(error) {
    return ERROR_TITLES[(error && error.code) || ""] || "Something went wrong";
  }

  function describeError(error) {
    if (!error) return "The action could not be completed.";
    return error.message || String(error);
  }

  function notifyError(error, fallbackTitle) {
    toast("error", fallbackTitle || errorTitle(error), describeError(error));
  }

  function toast(kind, title, message) {
    const children = ui.toastRegion.children;
    if (children.length >= 4) children[0].remove();
    const node = el(
      "div",
      kind === "error" ? "toast is-error" : kind === "info" ? "toast is-info" : "toast"
    );
    const copy = el("div", "toast-copy");
    copy.append(el("p", "toast-title", title));
    if (message) copy.append(el("p", "toast-message", message));
    node.append(copy);
    node.addEventListener("click", function () {
      node.remove();
    });
    ui.toastRegion.append(node);
    setTimeout(function () {
      if (node.isConnected) node.remove();
    }, 6000);
  }

  function showAlert(node, message, kind) {
    if (!node) return;
    clear(node);
    node.append(el("span", "", message));
    node.classList.toggle("is-info", kind === "info");
    node.hidden = false;
  }

  function hideAlert(node) {
    if (!node) return;
    node.hidden = true;
    node.textContent = "";
    node.classList.remove("is-info");
  }

  function showGlobalAlert(message, kind) {
    clear(ui.globalAlert);
    const box = el("div", kind === "info" ? "inline-alert is-info" : "inline-alert", message);
    const dismiss = el("button", "", "Dismiss");
    dismiss.type = "button";
    dismiss.addEventListener("click", function () {
      ui.globalAlert.hidden = true;
      clear(ui.globalAlert);
    });
    box.append(dismiss);
    ui.globalAlert.append(box);
    ui.globalAlert.hidden = false;
  }

  function openDialog(dialog) {
    if (!dialog || dialog.open) return;
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }

  function closeDialog(dialog) {
    if (dialog && dialog.open) dialog.close();
  }

  function formValues(form) {
    const values = {};
    new FormData(form).forEach(function (value, key) {
      values[key] = typeof value === "string" ? value : "";
    });
    return values;
  }

  function orderedSelectedRefs() {
    return state.utterances
      .map(function (item) {
        return item.ref;
      })
      .filter(function (ref) {
        return state.selection.has(ref);
      });
  }

  function renderProviderChip() {
    const status = state.provider;
    ui.providerDot.classList.remove("is-warn", "is-error");
    if (!status) {
      ui.providerLabel.textContent = "Local coach";
      ui.providerDetail.textContent = "Checking provider…";
      return;
    }
    if (status.mode === "mock") {
      ui.providerLabel.textContent = "Demo coach";
      ui.providerDetail.textContent = "Local rules · no network";
      ui.providerChip.title = status.limitations || "";
      return;
    }
    if (status.configured) {
      ui.providerLabel.textContent = "Configured provider";
      ui.providerDetail.textContent = (status.model || "model") + " · network";
    } else {
      ui.providerDot.classList.add("is-warn");
      ui.providerLabel.textContent = "Provider needs setup";
      ui.providerDetail.textContent = plural(status.missing.length, "item", "items") + " missing";
    }
    ui.providerChip.title = (status.base_url || "") + " " + (status.limitations || "");
  }

  function updateNavBadges() {
    const insightCount = state.insights.length;
    ui.coachNavCount.textContent = String(insightCount);
    ui.coachNavCount.hidden = insightCount === 0;
    const drafts = state.playbook.filter(function (entry) {
      return entry.status === "draft";
    }).length;
    ui.playbookNavCount.textContent = String(drafts);
    ui.playbookNavCount.hidden = drafts === 0;
  }

  function setView(view, options) {
    const opts = options || {};
    if (!Object.prototype.hasOwnProperty.call(VIEW_ELEMENTS, view)) return;
    state.view = view;
    document.querySelectorAll("[data-view]").forEach(function (button) {
      const active = button.dataset.view === view;
      button.classList.toggle("is-active", active);
      if (active) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    });
    Object.keys(VIEW_ELEMENTS).forEach(function (key) {
      VIEW_ELEMENTS[key].hidden = key !== view;
    });
    if (view === "desk") renderDesk();
    if (view === "coach") renderInsights();
    if (view === "playbook") {
      if (opts.playbookReady) renderPlaybookViewState();
      else void enterPlaybook();
    }
    if (view === "signals") void refreshSignals();
    if (view === "team" && window.ClearCommitTeamView) window.ClearCommitTeamView.refresh();
    if (opts.focus !== false) {
      const title = VIEW_TITLES[view];
      if (title) title.focus({ preventScroll: true });
    }
  }

  function syncActionAvailability() {
    const hasSession = Boolean(state.session);
    ui.importButton.disabled = !hasSession || state.busy;
    ui.addLineButton.disabled = !hasSession || state.busy;
    ui.importButton.title = hasSession ? "" : "Create a conversation first";
    ui.addLineButton.title = hasSession ? "" : "Create a conversation first";
    void updateSyncButton();
  }

  function renderSelection() {
    const refs = orderedSelectedRefs();
    const count = refs.length;
    const max = state.limits.max_evidence;
    const assistantMax = state.limits.max_assistant_evidence;
    ui.selectionCount.textContent = count + " selected";
    ui.quotaLabel.textContent = count + " / " + max;
    ui.assistantLimit.textContent = count + " / " + assistantMax;
    clear(ui.selectionRefs);
    if (!count) {
      ui.selectionRefs.append(el("span", "ref-empty", "No lines selected"));
    } else {
      refs.forEach(function (ref) {
        ui.selectionRefs.append(el("span", "ref-chip", ref));
      });
    }
    ui.analyzeButton.disabled = state.busy || count === 0 || !state.session;
    ui.askButton.disabled =
      state.busy || count === 0 || count > assistantMax || !state.session;
    ui.selectAllButton.disabled = state.busy || !state.utterances.length;
    ui.clearSelectionButton.disabled = state.busy || count === 0;
    let note = "Select up to " + max + " finalized lines.";
    if (count > 0 && count <= max) note = plural(count, "line", "lines") + " ready for the coach.";
    if (count > assistantMax) note += " The assistant accepts up to " + assistantMax + ".";
    ui.selectionNote.textContent = note;
    ui.analyzeButton.setAttribute("aria-busy", state.busy ? "true" : "false");
    syncActionAvailability();
  }

  function setBusy(value) {
    state.busy = Boolean(value);
    renderSelection();
  }

  function sessionMatches(item, query) {
    if (!query) return true;
    const haystack = [
      item.title,
      item.customer_name,
      item.company,
      item.rep_name,
      item.language_pair,
      item.occurred_on,
    ]
      .join(" ")
      .toLowerCase();
    return haystack.includes(query);
  }

  function renderSessionList() {
    clear(ui.sessionList);
    const query = state.sessionFilter.trim().toLowerCase();
    const sessions = state.sessions.filter(function (item) {
      return sessionMatches(item, query);
    });
    if (!sessions.length) {
      ui.sessionList.append(
        el(
          "p",
          "ref-empty",
          query ? "No conversations match that filter." : "No conversations yet."
        )
      );
      return;
    }
    sessions.forEach(function (item) {
      const active = Boolean(state.session && state.session.id === item.id);
      const button = el("button", active ? "session-item is-active" : "session-item");
      button.type = "button";
      button.setAttribute("aria-pressed", active ? "true" : "false");
      const top = el("span", "session-item-top");
      top.append(el("span", "session-title", item.title));
      if (item.is_sample) top.append(el("span", "sample-tag", "Sample"));
      const meta = el("span", "session-meta");
      meta.append(el("span", "", formatDate(item.occurred_on)));
      meta.append(el("span", "", plural(item.utterance_count, "line", "lines")));
      if (item.language_pair) meta.append(el("span", "", item.language_pair));
      button.append(top, meta);
      button.addEventListener("click", function () {
        void selectSession(item.id);
      });
      ui.sessionList.append(button);
    });
  }

  async function loadSessions() {
    const sessions = await bridge.call("list_sessions");
    state.sessions = Array.isArray(sessions) ? sessions : [];
    renderSessionList();
  }

  function resetSessionState() {
    state.selection = new Set();
    state.insights = [];
    state.selectedInsightId = null;
    state.insightFilter = "all";
    state.lastRun = null;
    state.assistantNotes = [];
    ui.briefCard.hidden = true;
    ui.askQuestion.value = "";
    hideAlert(ui.deskAnalysisError);
  }

  function applySessionDetail(detail, options) {
    const opts = options || {};
    state.session = detail.session;
    state.utterances = detail.utterances || [];
    state.assistantNotes = detail.assistant_notes || [];
    if (!opts.keepSelection) {
      const known = new Set(
        state.utterances.map(function (item) {
          return item.ref;
        })
      );
      state.selection = new Set(
        Array.from(state.selection).filter(function (ref) {
          return known.has(ref);
        })
      );
    }
    renderSessionList();
    renderDesk();
    renderAssistantNotes();
  }

  async function selectSession(sessionId) {
    if (!sessionId) return;
    try {
      const detail = await bridge.call("get_session", { session_id: sessionId });
      resetSessionState();
      applySessionDetail(detail, { keepSelection: true });
      await loadInsights(detail.session.id);
      renderSessionMeta();
      renderSelection();
    } catch (error) {
      notifyError(error, "Could not open that conversation");
    }
  }

  function renderDesk() {
    if (!state.session) {
      ui.deskDate.textContent = "Undated";
      ui.deskTitle.textContent = "Conversation desk";
      ui.deskSubtitle.textContent =
        "Create a conversation or open an existing transcript to begin.";
      clear(ui.deskMeta);
      clear(ui.transcriptList);
      setTranscriptEmpty(true, "No conversation open", "Create a conversation, then import a finalized transcript or add one line at a time.");
      renderSelection();
      return;
    }
    ui.deskDate.textContent = formatDate(state.session.occurred_on);
    ui.deskTitle.textContent = state.session.title;
    const parts = [];
    if (state.session.customer_name) parts.push(state.session.customer_name);
    if (state.session.company) parts.push(state.session.company);
    ui.deskSubtitle.textContent = parts.length
      ? parts.join(" · ") +
        ". Read the finalized transcript, then select the lines the coach should read."
      : "Read the finalized transcript, then select the lines the coach should read.";
    renderSessionMeta();
    renderTranscript();
    renderSelection();
  }

  function renderSessionMeta() {
    clear(ui.deskMeta);
    const session = state.session;
    if (!session) return;
    const add = function (text, className) {
      if (!text) return;
      ui.deskMeta.append(el("span", className ? "meta-chip " + className : "meta-chip", text));
    };
    add(session.company);
    add(session.customer_name);
    add("Rep: " + (session.rep_name || "You"));
    add(session.language_pair, "is-accent");
    add(plural(state.utterances.length, "finalized line", "finalized lines"), "is-final");
    if (state.insights.length) add(plural(state.insights.length, "finding", "findings"));
    if (session.is_sample) add("Sample conversation", "is-accent");
  }

  function setTranscriptEmpty(visible, heading, body) {
    ui.transcriptEmpty.hidden = !visible;
    if (!visible) return;
    const title = ui.transcriptEmpty.querySelector("h3");
    const copy = ui.transcriptEmpty.querySelector("p");
    if (title && heading) title.textContent = heading;
    if (copy && body) copy.textContent = body;
  }

  function renderTranscript() {
    clear(ui.transcriptList);
    if (!state.utterances.length) {
      setTranscriptEmpty(
        true,
        "No finished lines yet",
        "Import a finalized transcript or add one line at a time. This build does not listen to a microphone."
      );
      return;
    }
    setTranscriptEmpty(false);
    const fragment = document.createDocumentFragment();
    state.utterances.forEach(function (utterance) {
      const selected = state.selection.has(utterance.ref);
      const row = el(
        "li",
        "utterance is-" + utterance.speaker + (selected ? " is-selected" : "")
      );
      const wrap = el("label", "utterance-select");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.checked = selected;
      input.setAttribute("aria-label", "Select " + utterance.ref);
      input.addEventListener("change", function () {
        toggleSelection(utterance.ref, input.checked, row);
      });
      wrap.append(input, el("span", "checkmark"));
      const body = el("div", "utterance-body");
      const meta = el("div", "utterance-meta");
      meta.append(
        el("span", "speaker speaker-" + utterance.speaker, speakerLabel(utterance.speaker))
      );
      if (utterance.display_time) meta.append(el("span", "utterance-time", utterance.display_time));
      meta.append(el("span", "utterance-lang", String(utterance.language || "").toUpperCase()));
      meta.append(el("span", "utterance-ref", utterance.ref));
      body.append(meta);
      body.append(el("p", "utterance-original", utterance.original_text));
      if (utterance.translation) {
        body.append(el("p", "utterance-translation", "Translation: " + utterance.translation));
      }
      row.append(wrap, body);
      fragment.append(row);
    });
    ui.transcriptList.append(fragment);
  }

  function toggleSelection(ref, checked, row) {
    if (checked) {
      if (state.selection.size >= state.limits.max_evidence && !state.selection.has(ref)) {
        toast(
          "info",
          "Selection limit",
          "The coach reads up to " + state.limits.max_evidence + " lines at a time."
        );
        if (row) {
          const input = row.querySelector("input");
          if (input) input.checked = false;
        }
        return;
      }
      state.selection.add(ref);
    } else {
      state.selection.delete(ref);
    }
    if (row) row.classList.toggle("is-selected", state.selection.has(ref));
    hideAlert(ui.deskAnalysisError);
    renderSelection();
  }

  function selectFirstLines() {
    state.selection = new Set(
      state.utterances.slice(0, state.limits.max_evidence).map(function (item) {
        return item.ref;
      })
    );
    renderTranscript();
    renderSelection();
  }

  function clearSelection() {
    state.selection = new Set();
    renderTranscript();
    renderSelection();
  }

  function renderBrief(run, insights) {
    if (!run) {
      ui.briefCard.hidden = true;
      return;
    }
    ui.briefProvider.textContent = run.provider_name || "Coach";
    ui.briefSummary.textContent = run.summary || "";
    ui.briefCount.textContent = plural((insights || []).length, "observation", "observations");
    ui.briefCard.hidden = false;
  }

  async function runAnalysis() {
    if (state.busy || !state.session) return;
    const refs = orderedSelectedRefs();
    if (!refs.length) return;
    setBusy(true);
    hideAlert(ui.deskAnalysisError);
    ui.analyzeButton.classList.add("is-spinning");
    try {
      const result = await bridge.call("analyze", {
        session_id: state.session.id,
        evidence_refs: refs,
      });
      state.lastRun = result.run || null;
      if (result.run) renderBrief(result.run, result.insights || []);
      await loadInsights(state.session.id);
      await loadSessions();
      renderSessionMeta();
      toast(
        "info",
        "Coach brief ready",
        plural((result.insights || []).length, "observation", "observations") +
          " cited to your selected lines."
      );
    } catch (error) {
      showAlert(ui.deskAnalysisError, describeError(error));
      notifyError(error, "The coach could not analyze that evidence");
    } finally {
      setBusy(false);
      ui.analyzeButton.classList.remove("is-spinning");
    }
  }

  function renderAssistantNotes() {
    clear(ui.assistantNotes);
    if (!state.session) {
      ui.assistantNotes.append(
        el("p", "assistant-empty", "Open a conversation to ask about its evidence.")
      );
      return;
    }
    if (!state.assistantNotes.length) {
      ui.assistantNotes.append(
        el("p", "assistant-empty", "Answers appear here with citations to the selected lines.")
      );
      return;
    }
    state.assistantNotes
      .slice()
      .reverse()
      .forEach(function (note) {
        const card = el("article", "assistant-note");
        card.append(el("p", "assistant-note-q", note.question));
        card.append(el("p", "assistant-note-a", note.answer));
        const meta = el("div", "assistant-note-meta");
        (note.evidence_refs || []).forEach(function (ref) {
          meta.append(el("span", "meta-chip", ref));
        });
        meta.append(el("span", "meta-chip", note.provider_name || "Coach"));
        if (note.created_at) meta.append(el("span", "meta-chip", formatStamp(note.created_at)));
        card.append(meta);
        if (note.limitations) {
          card.append(el("p", "detail-limits", "Limits: " + note.limitations));
        }
        ui.assistantNotes.append(card);
      });
  }

  async function askAssistant(event) {
    if (event) event.preventDefault();
    if (state.busy || !state.session) return;
    const question = ui.askQuestion.value.trim();
    const refs = orderedSelectedRefs();
    const assistantMax = state.limits.max_assistant_evidence;
    if (!question) {
      toast("info", "Add a question", "Type what you want to know about the selected lines.");
      ui.askQuestion.focus();
      return;
    }
    if (!refs.length) {
      toast("info", "Select evidence", "Choose at least one line for the assistant to read.");
      return;
    }
    if (refs.length > assistantMax) {
      toast(
        "info",
        "Too many lines",
        "The assistant reads up to " + assistantMax + " lines at a time."
      );
      return;
    }
    setBusy(true);
    try {
      const note = await bridge.call("ask_assistant", {
        session_id: state.session.id,
        evidence_refs: refs,
        question: question,
      });
      state.assistantNotes.push(note);
      ui.askQuestion.value = "";
      renderAssistantNotes();
      toast(
        "info",
        "Answer ready",
        "Grounded in " + plural(refs.length, "selected line", "selected lines") + "."
      );
    } catch (error) {
      notifyError(error, "The assistant could not answer");
    } finally {
      setBusy(false);
    }
  }

  async function loadInsights(sessionId) {
    if (!sessionId) {
      state.insights = [];
      renderInsights();
      return;
    }
    try {
      const insights = await bridge.call("list_insights", { session_id: sessionId });
      state.insights = Array.isArray(insights) ? insights : [];
    } catch (error) {
      state.insights = [];
      notifyError(error, "Could not load findings");
    }
    if (
      state.selectedInsightId &&
      !state.insights.some(function (item) {
        return item.id === state.selectedInsightId;
      })
    ) {
      state.selectedInsightId = null;
    }
    renderInsights();
  }

  function filteredInsights() {
    if (state.insightFilter === "all") return state.insights;
    return state.insights.filter(function (item) {
      return item.type === state.insightFilter;
    });
  }

  function renderInsights() {
    updateNavBadges();
    renderCoachSummary();
    renderInsightFilters();
    clear(ui.insightList);
    ui.insightCountLabel.textContent = String(state.insights.length);
    if (!state.insights.length) {
      ui.coachGrid.hidden = true;
      ui.coachEmpty.hidden = false;
      clear(ui.insightDetail);
      return;
    }
    ui.coachEmpty.hidden = true;
    ui.coachGrid.hidden = false;
    const insights = filteredInsights();
    if (
      !state.selectedInsightId ||
      !insights.some(function (item) {
        return item.id === state.selectedInsightId;
      })
    ) {
      state.selectedInsightId = insights.length ? insights[0].id : null;
    }
    if (!insights.length) {
      ui.insightList.append(el("p", "ref-empty", "No findings with this filter."));
    }
    insights.forEach(function (insight) {
      const active = insight.id === state.selectedInsightId;
      const button = el("button", active ? "insight-item is-active" : "insight-item");
      button.type = "button";
      const top = el("span", "insight-top");
      top.append(el("span", "type-dot type-" + insight.type));
      top.append(
        el("span", "insight-type", insight.type_label || TYPE_LABELS[insight.type] || insight.type)
      );
      top.append(el("span", "insight-conf", insight.confidence || ""));
      button.append(top);
      button.append(el("span", "insight-item-title", insight.title));
      button.append(
        el("span", "insight-item-refs", (insight.evidence_refs || []).join(" · "))
      );
      button.addEventListener("click", function () {
        state.selectedInsightId = insight.id;
        renderInsights();
      });
      ui.insightList.append(button);
    });
    renderInsightDetail();
  }

  function renderCoachSummary() {
    const session = state.session;
    ui.coachContext.textContent = session
      ? session.title + " · " + formatDate(session.occurred_on)
      : "No selection analyzed";
    clear(ui.coachMeta);
    if (!state.insights.length) {
      ui.coachSummary.hidden = true;
      return;
    }
    ui.coachMeta.append(
      el("span", "meta-chip", plural(state.insights.length, "finding", "findings"))
    );
    if (session && session.language_pair) {
      ui.coachMeta.append(el("span", "meta-chip is-accent", session.language_pair));
    }
    const refs = new Set();
    state.insights.forEach(function (insight) {
      (insight.evidence_refs || []).forEach(function (ref) {
        refs.add(ref);
      });
    });
    ui.coachMeta.append(el("span", "meta-chip", plural(refs.size, "evidence line", "evidence lines")));
    const latest =
      state.lastRun ||
      {
        summary: state.insights[0].run_summary,
        limitations: state.insights[0].run_limitations,
        provider_name: state.insights[0].provider_name,
      };
    if (latest && latest.summary) {
      ui.coachSummary.hidden = false;
      ui.coachSummaryText.textContent = latest.summary;
      ui.coachProvider.textContent = latest.provider_name || "Coach";
      ui.coachLimitations.textContent = latest.limitations || "";
    } else {
      ui.coachSummary.hidden = true;
    }
  }

  function renderInsightFilters() {
    clear(ui.insightFilters);
    const types = ["all"].concat(Object.keys(TYPE_LABELS));
    types.forEach(function (type) {
      const count =
        type === "all"
          ? state.insights.length
          : state.insights.filter(function (item) {
              return item.type === type;
            }).length;
      if (type !== "all" && count === 0) return;
      const button = el("button", "filter-chip");
      button.type = "button";
      button.textContent = (type === "all" ? "All" : TYPE_LABELS[type]) + " " + count;
      if (state.insightFilter === type) button.classList.add("is-active");
      button.setAttribute("aria-pressed", state.insightFilter === type ? "true" : "false");
      button.addEventListener("click", function () {
        state.insightFilter = type;
        state.selectedInsightId = null;
        renderInsights();
      });
      ui.insightFilters.append(button);
    });
  }

  function detailSection(title) {
    const node = el("section", "detail-section");
    node.append(el("h3", "", title));
    return node;
  }

  function renderInsightDetail() {
    clear(ui.insightDetail);
    if (!state.insights.length) return;
    const insight = state.insights.find(function (item) {
      return item.id === state.selectedInsightId;
    });
    if (!insight) {
      ui.insightDetail.append(el("p", "ref-empty", "Choose a finding to review its evidence."));
      return;
    }
    const inner = el("div", "detail-inner");
    const top = el("div", "detail-top");
    const copy = el("div");
    const typeRow = el("div", "detail-type-row");
    typeRow.append(el("span", "type-dot type-" + insight.type));
    typeRow.append(
      el("span", "insight-type", insight.type_label || TYPE_LABELS[insight.type] || "Finding")
    );
    copy.append(typeRow);
    copy.append(el("h2", "detail-title", insight.title));
    top.append(copy);
    top.append(el("span", "detail-confidence", (insight.confidence || "medium") + " confidence"));
    inner.append(top);

    const observation = detailSection("Observation");
    observation.append(el("p", "detail-observation", insight.observation));
    inner.append(observation);

    const why = detailSection("Why it matters");
    why.append(el("p", "detail-why", insight.why_it_matters));
    inner.append(why);

    const evidenceSection = detailSection("Evidence");
    const list = el("div", "evidence-list");
    (insight.evidence || []).forEach(function (item) {
      const figure = el("figure", item.speaker === "rep" ? "evidence-quote is-rep" : "evidence-quote");
      figure.append(el("blockquote", "", "“" + item.quote + "”"));
      const caption = el("figcaption");
      caption.append(el("span", "", item.ref));
      caption.append(el("span", "", speakerLabel(item.speaker)));
      if (item.spoken_at) caption.append(el("span", "", item.spoken_at));
      if (item.language) caption.append(el("span", "", String(item.language).toUpperCase()));
      figure.append(caption);
      if (item.translation) {
        figure.append(el("p", "evidence-translation", "Translation: " + item.translation));
      }
      list.append(figure);
    });
    if (!(insight.evidence || []).length) {
      list.append(el("p", "ref-empty", "No evidence recorded."));
    }
    evidenceSection.append(list);
    inner.append(evidenceSection);

    const alternative = detailSection("Suggested alternative");
    const box = el("div", "alternative-box");
    box.append(el("p", "alternative-copy", insight.proposed_alternative));
    const row = el("div", "form-row");
    const use = el("button", "text-button alt-copy", "Select these lines");
    use.type = "button";
    use.addEventListener("click", function () {
      focusEvidence(insight);
    });
    row.append(use);
    box.append(row);
    alternative.append(box);
    inner.append(alternative);

    const action = detailSection("Recommended action");
    action.append(el("p", "action-line", insight.recommended_action));
    inner.append(action);

    if (insight.limitations) {
      const limits = detailSection("Limits");
      limits.append(el("p", "detail-limits", insight.limitations));
      inner.append(limits);
    }

    const actions = el("div", "detail-actions");
    const promote = el("button", "button button-primary", "Turn into playbook draft");
    promote.type = "button";
    promote.addEventListener("click", function () {
      void promoteInsight(insight);
    });
    const select = el("button", "button button-quiet", "Select evidence in transcript");
    select.type = "button";
    select.addEventListener("click", function () {
      focusEvidence(insight);
    });
    actions.append(promote, select);
    inner.append(actions);

    ui.insightDetail.append(inner);
  }

  function focusEvidence(insight) {
    const refs = (insight.evidence_refs || []).slice(0, state.limits.max_evidence);
    state.selection = new Set(refs);
    renderTranscript();
    renderSelection();
    setView("desk", { focus: false });
    ui.deskTitle.focus({ preventScroll: true });
    const first = ui.transcriptList.querySelector(".utterance.is-selected");
    if (first) first.scrollIntoView({ block: "center" });
    toast(
      "info",
      "Evidence selected",
      plural(refs.length, "line", "lines") + " selected for the coach and assistant."
    );
  }

  async function promoteInsight(insight) {
    try {
      const entry = await bridge.call("create_playbook", { insight_id: insight.id });
      state.selectedPlaybookId = entry.id;
      state.playbookEntry = entry;
      state.playbookFilter = "all";
      syncPlaybookFilterButtons();
      fillPlaybookForm(entry);
      await loadPlaybook();
      setView("playbook", { playbookReady: true });
      renderPlaybookList();
      ui.playbookEmpty.hidden = true;
      ui.playbookForm.hidden = false;
      toast(
        "info",
        entry.created === false ? "Already in the playbook" : "Draft created",
        "“" + entry.title + "” is waiting for review."
      );
    } catch (error) {
      notifyError(error, "Could not create a playbook draft");
    }
  }

  function filteredPlaybook() {
    if (state.playbookFilter === "all") return state.playbook;
    return state.playbook.filter(function (entry) {
      return entry.status === state.playbookFilter;
    });
  }

  function syncPlaybookFilterButtons() {
    document.querySelectorAll("[data-playbook-filter]").forEach(function (button) {
      const active = button.dataset.playbookFilter === state.playbookFilter;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  async function loadPlaybook() {
    const entries = await bridge.call("list_playbook");
    state.playbook = Array.isArray(entries) ? entries : [];
    renderPlaybookList();
    updateNavBadges();
  }

  function renderPlaybookList() {
    clear(ui.playbookList);
    const entries = filteredPlaybook();
    ui.playbookCountLabel.textContent = String(entries.length);
    if (!entries.length) {
      ui.playbookList.append(
        el(
          "p",
          "ref-empty",
          state.playbook.length ? "No entries with this filter." : "No playbook entries yet."
        )
      );
      return;
    }
    entries.forEach(function (entry) {
      const active = entry.id === state.selectedPlaybookId;
      const button = el("button", active ? "playbook-item is-active" : "playbook-item");
      button.type = "button";
      button.append(el("span", "playbook-item-title", entry.title));
      const meta = el("span", "playbook-item-meta");
      meta.append(
        el("span", entry.status === "approved" ? "pb-status-dot is-approved" : "pb-status-dot")
      );
      meta.append(el("span", "", entry.status === "approved" ? "Approved" : "Draft"));
      meta.append(el("span", "", "· " + (TYPE_LABELS[entry.category] || "Guidance")));
      meta.append(el("span", "", "· " + plural((entry.evidence_refs || []).length, "ref", "refs")));
      button.append(meta);
      button.addEventListener("click", function () {
        void selectPlaybookEntry(entry.id);
      });
      ui.playbookList.append(button);
    });
  }

  async function enterPlaybook() {
    try {
      await loadPlaybook();
    } catch (error) {
      notifyError(error, "Could not load the playbook");
      return;
    }
    renderPlaybookViewState();
  }

  function renderPlaybookViewState() {
    renderPlaybookList();
    const entries = filteredPlaybook();
    if (!entries.length) {
      state.selectedPlaybookId = null;
      state.playbookEntry = null;
      ui.playbookEmpty.hidden = false;
      ui.playbookForm.hidden = true;
      const title = ui.playbookEmpty.querySelector("h3");
      const copy = ui.playbookEmpty.querySelector("p");
      if (title) {
        title.textContent = state.playbook.length ? "No entries with this filter" : "No entry selected";
      }
      if (copy) {
        copy.textContent = state.playbook.length
          ? "Switch the filter or promote a coaching observation into the playbook."
          : "Promote an observation from the sales coach, or choose an existing playbook entry. Approval requires a reviewer name, a discovery question, and evidence.";
      }
      return;
    }
    if (
      !state.selectedPlaybookId ||
      !entries.some(function (entry) {
        return entry.id === state.selectedPlaybookId;
      })
    ) {
      void selectPlaybookEntry(entries[0].id);
      return;
    }
    if (!state.playbookEntry || state.playbookEntry.id !== state.selectedPlaybookId) {
      void selectPlaybookEntry(state.selectedPlaybookId);
      return;
    }
    ui.playbookEmpty.hidden = true;
    ui.playbookForm.hidden = false;
  }

  async function selectPlaybookEntry(entryId) {
    if (state.playbookEntry && state.playbookEntry.id === entryId && !ui.playbookForm.hidden) {
      state.selectedPlaybookId = entryId;
      renderPlaybookList();
      return;
    }
    try {
      const entry = await bridge.call("get_playbook", { entry_id: entryId });
      state.selectedPlaybookId = entry.id;
      state.playbookEntry = entry;
      fillPlaybookForm(entry);
      renderPlaybookList();
      ui.playbookEmpty.hidden = true;
      ui.playbookForm.hidden = false;
    } catch (error) {
      notifyError(error, "Could not open that playbook entry");
    }
  }

  function fillPlaybookForm(entry) {
    const approved = entry.status === "approved";
    ui.pbEyebrow.textContent = approved ? "Approved guidance" : "Playbook entry";
    ui.pbHeading.textContent = entry.title || "Untitled entry";
    ui.pbStatus.textContent = approved ? "Approved" : "Draft";
    ui.pbStatus.classList.toggle("is-approved", approved);
    ui.pbUpdated.textContent = entry.updated_at ? "Updated " + formatStamp(entry.updated_at) : "";
    ui.pbTitle.value = entry.title || "";
    ui.pbScenario.value = entry.scenario || "";
    ui.pbCategory.value = entry.category || "objection";
    ui.pbObjection.value = entry.objection || "";
    ui.pbResponse.value = entry.approved_response || "";
    ui.pbQuestions.value = (entry.discovery_questions || []).join("\n");
    ui.pbReviewer.value =
      entry.approved_by || (state.settings && state.settings.reviewer_name) || "";
    ui.pbNote.value = "";
    clear(ui.pbEvidenceRefs);
    const refs = entry.evidence_refs || [];
    if (!refs.length) {
      ui.pbEvidenceRefs.append(el("span", "ref-empty", "No linked evidence"));
    } else {
      refs.forEach(function (ref) {
        ui.pbEvidenceRefs.append(el("span", "ref-chip", ref));
      });
    }
    ui.pbEvidenceSummary.textContent = entry.evidence_summary || "No evidence summary recorded.";
    ui.pbApprove.disabled = approved;
    ui.pbApprove.textContent = approved ? "Approved" : "Approve for the team";
    ui.pbSave.textContent = approved ? "Save changes" : "Save draft";
    ui.pbSaveHint.textContent = approved
      ? "Saving changes to approved guidance reopens review."
      : "Saved drafts stay local until a named reviewer approves them.";
    ui.pbGateNote.textContent =
      approved && entry.approved_by
        ? "Approved by " +
          entry.approved_by +
          " on " +
          formatStamp(entry.approved_at) +
          ". This local record is not an account or signature service."
        : "A named reviewer approves this guidance. Approval is a local record, not an account or signature service.";
    renderPlaybookReviews(entry);
    hideAlert(ui.pbError);
  }

  function renderPlaybookReviews(entry) {
    clear(ui.pbReviews);
    const reviews = (entry.reviews || []).slice().reverse();
    if (!reviews.length) {
      ui.pbReviews.append(el("li", "", "No review activity yet."));
      return;
    }
    reviews.forEach(function (review) {
      const item = el("li");
      item.append(
        el(
          "span",
          "review-action",
          review.action === "reopened" ? "Review reopened" : review.action
        )
      );
      item.append(
        el("span", "review-meta", review.reviewer + " · " + formatStamp(review.created_at))
      );
      if (review.note) item.append(el("span", "review-note", review.note));
      ui.pbReviews.append(item);
    });
  }

  function collectPlaybookFields() {
    return {
      title: ui.pbTitle.value.trim(),
      scenario: ui.pbScenario.value.trim(),
      objection: ui.pbObjection.value.trim(),
      approved_response: ui.pbResponse.value.trim(),
      discovery_questions: ui.pbQuestions.value
        .split("\n")
        .map(function (line) {
          return line.trim();
        })
        .filter(Boolean),
      category: ui.pbCategory.value,
    };
  }

  function applyPlaybookEntry(entry) {
    state.playbookEntry = entry;
    state.selectedPlaybookId = entry.id;
    const index = state.playbook.findIndex(function (item) {
      return item.id === entry.id;
    });
    if (index >= 0) state.playbook[index] = entry;
    else state.playbook.unshift(entry);
    fillPlaybookForm(entry);
    renderPlaybookList();
    updateNavBadges();
  }

  function setPlaybookFilter(filter) {
    state.playbookFilter = filter;
    syncPlaybookFilterButtons();
    renderPlaybookViewState();
  }

  async function savePlaybookEntry(event) {
    if (event) event.preventDefault();
    if (!state.playbookEntry) return;
    hideAlert(ui.pbError);
    const previous = state.playbookEntry;
    const fields = collectPlaybookFields();
    const reviewer = ui.pbReviewer.value.trim();
    ui.pbSave.disabled = true;
    try {
      const entry = await bridge.call("save_playbook", {
        entry_id: previous.id,
        fields: fields,
        reviewer: reviewer,
      });
      applyPlaybookEntry(entry);
      if (previous.status === "approved" && entry.status === "draft") {
        toast("info", "Review reopened", "Editing approved guidance returned it to draft.");
      } else {
        toast("info", "Draft saved", "“" + entry.title + "” is up to date.");
      }
    } catch (error) {
      showAlert(ui.pbError, describeError(error));
      notifyError(error, "Could not save the playbook entry");
    } finally {
      ui.pbSave.disabled = false;
    }
  }

  async function approvePlaybook() {
    if (!state.playbookEntry) return;
    hideAlert(ui.pbError);
    const fields = collectPlaybookFields();
    const reviewer = ui.pbReviewer.value.trim();
    const note = ui.pbNote.value.trim();
    const missing = [];
    if (!fields.title) missing.push("Title");
    if (!fields.scenario) missing.push("Communication scenario");
    if (!fields.objection) missing.push("Customer moment or objection");
    if (!fields.approved_response) missing.push("Approved response");
    if (!fields.discovery_questions.length) missing.push("At least one discovery question");
    if (missing.length) {
      showAlert(ui.pbError, "Complete before approval: " + missing.join(", ") + ".");
      return;
    }
    if (!reviewer) {
      showAlert(ui.pbError, "Enter the reviewer name before approving.");
      ui.pbReviewer.focus();
      return;
    }
    ui.pbApprove.disabled = true;
    try {
      const saved = await bridge.call("save_playbook", {
        entry_id: state.playbookEntry.id,
        fields: fields,
        reviewer: reviewer,
      });
      const entry = await bridge.call("approve_playbook", {
        entry_id: saved.id,
        reviewer: reviewer,
        note: note,
      });
      applyPlaybookEntry(entry);
      toast("info", "Approved for the team", "Reviewer: " + reviewer + ".");
    } catch (error) {
      showAlert(ui.pbError, describeError(error));
      notifyError(error, "Could not approve this guidance");
    } finally {
      ui.pbApprove.disabled = state.playbookEntry
        ? state.playbookEntry.status === "approved"
        : false;
    }
  }

  async function resetPlaybook() {
    if (!state.playbookEntry) return;
    try {
      const entry = await bridge.call("get_playbook", { entry_id: state.playbookEntry.id });
      state.playbookEntry = entry;
      state.selectedPlaybookId = entry.id;
      fillPlaybookForm(entry);
      renderPlaybookList();
      toast("info", "Changes discarded", "The saved version is restored.");
    } catch (error) {
      notifyError(error, "Could not restore that entry");
    }
  }

  async function refreshPlaybook() {
    try {
      await loadPlaybook();
      if (state.selectedPlaybookId) {
        const entry = await bridge.call("get_playbook", {
          entry_id: state.selectedPlaybookId,
        });
        state.playbookEntry = entry;
        fillPlaybookForm(entry);
      }
      renderPlaybookViewState();
      toast("info", "Playbook refreshed");
    } catch (error) {
      notifyError(error, "Could not refresh the playbook");
    }
  }

  function renderMeters(target, values, emptyText) {
    clear(target);
    const entries = Object.entries(values || {}).sort(function (a, b) {
      return Number(b[1]) - Number(a[1]);
    });
    if (!entries.length) {
      target.append(el("p", "meter-empty", emptyText));
      return;
    }
    const max = Math.max.apply(
      null,
      entries.map(function (entry) {
        return Number(entry[1]) || 0;
      })
    );
    entries.forEach(function (entry) {
      const key = entry[0];
      const count = Number(entry[1]) || 0;
      const row = el("div", "meter-row");
      const top = el("div", "meter-top");
      top.append(el("span", "meter-label", TYPE_LABELS[key] || key));
      top.append(el("span", "meter-value", String(count)));
      const bar = document.createElement("progress");
      bar.max = Math.max(max, 1);
      bar.value = count;
      bar.setAttribute("aria-label", (TYPE_LABELS[key] || key) + ": " + count);
      row.append(top, bar);
      target.append(row);
    });
  }

  function renderSignals(preview) {
    if (!preview) return;
    const counts = preview.counts || {};
    ui.signalApproved.textContent = String(counts.playbook_approved || 0);
    ui.signalDrafts.textContent = String(counts.playbook_draft || 0);
    ui.signalSessions.textContent = String(counts.sessions || 0);
    ui.signalUtterances.textContent = String(counts.utterances || 0);
    ui.signalInsights.textContent = String(counts.insights || 0);
    ui.signalCoverage.textContent =
      plural(preview.approved_sessions || 0, "approved conversation contributes", "approved conversations contribute") +
      " guidance.";
    ui.consentNote.textContent =
      preview.consent_note ||
      "Team Insights is a design preview. This build does not aggregate employee performance scores.";
    renderMeters(ui.signalCategories, preview.approved_by_category, "No approved guidance yet.");
    renderMeters(ui.signalMix, preview.insight_types, "No coaching findings yet.");
  }

  async function refreshSignals() {
    try {
      const preview = await bridge.call("refresh_preview");
      state.preview = preview;
      renderSignals(preview);
    } catch (error) {
      notifyError(error, "Could not refresh team signals");
    }
  }

  function renderSettingsStatus(status, message, tone) {
    clear(ui.settingsStatus);
    if (!status) return;
    const list = el("div", "status-list");
    const addRow = function (label, value, missing) {
      const row = el("div", missing ? "status-row is-missing" : "status-row");
      row.append(el("span", "status-bullet"));
      const text = el("span");
      text.append(el("strong", "", label + ": "));
      text.append(document.createTextNode(value));
      row.append(text);
      list.append(row);
    };
    addRow("Mode", status.mode_label || status.mode || "");
    if (status.mode === "openai_compatible") {
      addRow(
        "API key",
        status.key_present ? "present in the environment" : "missing (set " + status.key_env + ")",
        !status.key_present
      );
      addRow("Base URL", status.base_url || "not set", !status.base_url);
      addRow("Model", status.model || "not set", !status.model);
    }
    ui.settingsStatus.append(list);
    const detail = message || status.limitations || "";
    if (detail) {
      const note = el(
        "p",
        tone === "ok" ? "status-message is-ok" : tone === "bad" ? "status-message is-bad" : "status-message",
        detail
      );
      ui.settingsStatus.append(note);
    }
  }

  function openSettings() {
    if (!state.settings) return;
    const mode = state.settings.provider_mode === "openai_compatible" ? "openai_compatible" : "mock";
    ui.settingsForm.querySelectorAll('input[name="provider_mode"]').forEach(function (radio) {
      radio.checked = radio.value === mode;
    });
    ui.settingsBaseUrl.value = state.settings.base_url || "";
    ui.settingsModel.value = state.settings.model || "";
    ui.settingsTimeout.value = state.settings.timeout_s || 25;
    ui.settingsReviewer.value = state.settings.reviewer_name || "";
    hideAlert(ui.settingsError);
    renderSettingsStatus(state.provider, "", "");
    openDialog(ui.settingsDialog);
  }

  function collectSettings() {
    const modeInput = ui.settingsForm.querySelector('input[name="provider_mode"]:checked');
    return {
      provider_mode: modeInput ? modeInput.value : "mock",
      base_url: ui.settingsBaseUrl.value.trim(),
      model: ui.settingsModel.value.trim(),
      timeout_s: Number(ui.settingsTimeout.value || 25),
      reviewer_name: ui.settingsReviewer.value.trim(),
    };
  }

  async function persistSettings(options) {
    const opts = options || {};
    hideAlert(ui.settingsError);
    let result;
    try {
      result = await bridge.call("save_settings", collectSettings());
    } catch (error) {
      showAlert(ui.settingsError, describeError(error));
      if (opts.notify !== false) notifyError(error, "Could not save settings");
      return null;
    }
    state.settings = result.settings;
    state.provider = result.provider;
    renderProviderChip();
    renderSettingsStatus(result.provider, "", "");
    if (opts.announce) {
      toast("info", "Settings saved", "Provider and reviewer settings are up to date.");
    }
    if (opts.close) closeDialog(ui.settingsDialog);
    return result;
  }

  async function testProvider() {
    ui.testProvider.disabled = true;
    hideAlert(ui.settingsError);
    try {
      const saved = await persistSettings({ notify: false });
      if (!saved) return;
      const result = await bridge.call("test_provider");
      const ok = Boolean(result && result.ok);
      renderSettingsStatus(
        state.provider,
        (result && result.message) || (ok ? "The provider responded." : "The provider did not respond."),
        ok ? "ok" : "bad"
      );
      toast(
        ok ? "info" : "error",
        ok ? "Connection check passed" : "Connection check failed",
        (result && result.message) || ""
      );
    } catch (error) {
      showAlert(ui.settingsError, describeError(error));
      notifyError(error, "The connection check failed");
    } finally {
      ui.testProvider.disabled = false;
    }
  }

  function openNewSession() {
    hideAlert(ui.newSessionError);
    ui.newTitle.value = "";
    ui.newCustomer.value = "";
    ui.newCompany.value = "";
    ui.newRep.value = "You";
    ui.newDate.value = todayIso();
    ui.newCustomerLanguage.value = "en";
    ui.newRepLanguage.value = "en";
    openDialog(ui.newSessionDialog);
    ui.newTitle.focus();
  }

  async function createSessionFromDialog() {
    hideAlert(ui.newSessionError);
    const values = formValues(ui.newSessionForm);
    try {
      const detail = await bridge.call("create_session", values);
      await loadSessions();
      resetSessionState();
      applySessionDetail(detail);
      await loadInsights(detail.session.id);
      renderSessionMeta();
      renderSelection();
      closeDialog(ui.newSessionDialog);
      setView("desk", { focus: false });
      toast("info", "Conversation created", detail.session.title);
    } catch (error) {
      showAlert(ui.newSessionError, describeError(error));
    }
  }

  function openImport() {
    if (!state.session) {
      toast("info", "Create a conversation first", "Imports attach to a conversation.");
      openNewSession();
      return;
    }
    hideAlert(ui.importError);
    ui.importText.value = "";
    openDialog(ui.importDialog);
    ui.importText.focus();
  }

  async function importTranscript() {
    if (!state.session) return;
    hideAlert(ui.importError);
    const transcript = ui.importText.value;
    if (!transcript.trim()) {
      showAlert(ui.importError, "Paste at least one transcript line.");
      ui.importText.focus();
      return;
    }
    const before = state.utterances.length;
    const button = ui.importForm.querySelector('button[type="submit"]');
    button.disabled = true;
    try {
      const detail = await bridge.call("import_transcript", {
        session_id: state.session.id,
        transcript: transcript,
      });
      applySessionDetail(detail, { keepSelection: true });
      await loadSessions();
      renderSessionMeta();
      renderSelection();
      closeDialog(ui.importDialog);
      toast(
        "info",
        "Transcript imported",
        plural(detail.utterances.length - before, "line", "lines") + " added."
      );
    } catch (error) {
      showAlert(ui.importError, describeError(error));
    } finally {
      button.disabled = false;
    }
  }

  function openAddLine() {
    if (!state.session) {
      toast("info", "Create a conversation first", "Lines attach to a conversation.");
      openNewSession();
      return;
    }
    hideAlert(ui.addLineError);
    ui.lineSpeaker.value = "customer";
    ui.lineTime.value = "";
    ui.lineOriginal.value = "";
    ui.lineTranslation.value = "";
    ui.lineLanguage.value = state.session.customer_language || "en";
    openDialog(ui.addLineDialog);
    ui.lineOriginal.focus();
  }

  async function addLine() {
    if (!state.session) return;
    hideAlert(ui.addLineError);
    const values = formValues(ui.addLineForm);
    if (!values.original_text || !values.original_text.trim()) {
      showAlert(ui.addLineError, "Enter the original words.");
      ui.lineOriginal.focus();
      return;
    }
    const button = ui.addLineForm.querySelector('button[type="submit"]');
    button.disabled = true;
    try {
      const utterance = await bridge.call(
        "add_utterance",
        Object.assign({ session_id: state.session.id }, values)
      );
      const detail = await bridge.call("get_session", { session_id: state.session.id });
      applySessionDetail(detail, { keepSelection: true });
      await loadSessions();
      renderSessionMeta();
      renderSelection();
      closeDialog(ui.addLineDialog);
      toast("info", "Line added", utterance.ref + " is ready for analysis.");
    } catch (error) {
      showAlert(ui.addLineError, describeError(error));
    } finally {
      button.disabled = false;
    }
  }

  const MODE_KEY = "clearcommit.teams.mode";

  function readMode() {
    try {
      const stored = localStorage.getItem(MODE_KEY);
      return stored === "company" || stored === "individual" ? stored : null;
    } catch (error) {
      return null;
    }
  }

  function writeMode(mode) {
    try {
      localStorage.setItem(MODE_KEY, mode);
    } catch (error) {
      /* storage unavailable: the choice simply isn't remembered */
    }
  }

  function applyMode(mode) {
    state.mode = mode;
    if (ui.modeChip) {
      ui.modeChip.dataset.mode = mode;
      ui.modeChip.textContent = mode === "company" ? "Company" : "Individual";
      ui.modeChip.title =
        mode === "company"
          ? "Using ClearCommit with a team. Click to change."
          : "Using ClearCommit on your own. Click to change.";
    }
  }

  function openOnboarding() {
    const dialog = document.getElementById("onboarding-dialog");
    if (!dialog) return;
    const note = document.getElementById("onboarding-note");
    if (note) {
      note.textContent =
        "Personal conversations stay in this workspace unless you explicitly share one. " +
        "Joining a team later does not move them.";
    }
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }

  function closeOnboarding() {
    const dialog = document.getElementById("onboarding-dialog");
    if (!dialog) return;
    if (typeof dialog.close === "function") dialog.close();
    else dialog.removeAttribute("open");
  }

  function chooseMode(mode) {
    writeMode(mode);
    applyMode(mode);
    closeOnboarding();
    if (mode === "company") {
      setView("team");
      if (window.ClearCommitTeamView) window.ClearCommitTeamView.refresh();
    } else {
      setView("desk");
    }
  }

  // The team view switches the local workspace to the signed-in account. It
  // needs the same bridge instance, and the local UI must reload afterwards.
  window.ClearCommitLocalBridge = bridge;
  window.ClearCommitLocalWorkspaceChanged = function () {
    void boot();
  };
  // Signing in or out changes whether a conversation can be saved to the cloud.
  window.ClearCommitSyncStateChanged = function () {
    void updateSyncButton();
  };

  // Runs before the local workspace switches accounts. An open guest
  // conversation is uploaded first so signing in does not orphan it.
  window.ClearCommitBeforeWorkspaceSwitch = async function () {
    if (!state.session) return;
    const net = window.ClearCommitNet;
    if (!net || !net.signedIn()) return;
    try {
      const link = await bridge.call("get_cloud_link", { session_id: state.session.id });
      if (link.cloud_conversation_id) return;
      await syncCurrentConversationToCloud();
    } catch (error) {
      showGlobalAlert(
        "This conversation could not be saved to the cloud before switching accounts. " +
          "It stays in the guest workspace on this device.",
        "warn"
      );
    }
  };

  function initOnboarding() {
    const individual = document.getElementById("choose-individual");
    const company = document.getElementById("choose-company");
    if (individual) {
      individual.addEventListener("click", function () {
        chooseMode("individual");
      });
    }
    if (company) {
      company.addEventListener("click", function () {
        chooseMode("company");
      });
    }
    if (ui.modeChip) {
      ui.modeChip.addEventListener("click", function () {
        openOnboarding();
      });
    }
  }

  async function syncCurrentConversationToCloud() {
    const net = window.ClearCommitNet;
    const localId = state.session.id;
    const payload = await bridge.call("transcript_payload", { session_id: localId });
    if (!payload.utterances.length) {
      throw new Error("This conversation has no lines to save.");
    }
    const workspace = await net.call("POST", "/api/workspace", {});
    const created = await net.call("POST", "/api/orgs/" + workspace.org_id + "/conversations", {
      title: payload.title,
      language: payload.language,
      client_ref: localId,
      source: "desktop",
    });
    await net.call(
      "POST",
      "/api/orgs/" + workspace.org_id + "/conversations/" + created.conversation_id + "/utterances",
      { utterances: payload.utterances }
    );
    await bridge.call("set_cloud_link", {
      session_id: localId,
      cloud_conversation_id: created.conversation_id,
    });
    return created.conversation_id;
  }

  async function saveToCloud() {
    if (state.busy) return;
    if (!state.session) {
      showGlobalAlert("Open a conversation first.", "info");
      return;
    }
    const net = window.ClearCommitNet;
    if (!net || !net.signedIn()) {
      showGlobalAlert(
        "Sign in to the team workspace first. Your conversation stays on this device until then.",
        "info"
      );
      return;
    }
    setBusy(true);
    if (ui.syncButtonLabel) ui.syncButtonLabel.textContent = "Saving…";
    try {
      const link = await bridge.call("get_cloud_link", { session_id: state.session.id });
      if (link.cloud_conversation_id) {
        showGlobalAlert("This conversation is already saved to the cloud.", "info");
        return;
      }
      await syncCurrentConversationToCloud();
      showGlobalAlert(
        "Saved to the cloud. It is private to your account until you share it.",
        "ok"
      );
    } catch (error) {
      if (error && error.code === "network_error") {
        showGlobalAlert(
          "The cloud is unreachable. This conversation was NOT saved to the cloud.",
          "warn"
        );
      } else {
        notifyError(error, "Could not save to the cloud");
      }
    } finally {
      setBusy(false);
      updateSyncButton();
    }
  }
  async function updateSyncButton() {
    if (!ui.syncButton) return;
    const net = window.ClearCommitNet;
    if (!state.session || !net || !net.signedIn()) {
      ui.syncButton.hidden = true;
      return;
    }
    ui.syncButton.hidden = false;
    try {
      const link = await bridge.call("get_cloud_link", { session_id: state.session.id });
      const saved = Boolean(link.cloud_conversation_id);
      if (ui.syncButtonLabel) {
        ui.syncButtonLabel.textContent = saved ? "Saved to cloud" : "Save to cloud";
      }
      ui.syncButton.disabled = state.busy || saved;
      ui.syncButton.title = saved
        ? "This conversation already exists in your cloud workspace."
        : "Save a private copy to your account.";
    } catch (error) {
      ui.syncButton.disabled = state.busy;
    }
  }
  async function loadExampleConversation() {
    if (state.busy) return;
    setBusy(true);
    try {
      const created = await bridge.call("create_session", {
        title: "Example call (sample) — renewal pricing",
        customer_name: "Example customer",
        company: "Example company",
        rep_name: "You",
        customer_language: "en",
        rep_language: "en",
        occurred_on: new Date().toISOString().slice(0, 10),
      });
      const sessionId = created.session.id;
      await bridge.call("import_transcript", {
        session_id: sessionId,
        transcript: [
          "[00:04] Customer: Thanks for making time. We want to renew, but the annual price is a concern.",
          "[00:19] Rep: I understand. It is a bigger number than last year.",
          "[00:31] Customer: Right. And I am not clear on what the new tier actually includes.",
          "[00:48] Rep: The main difference is the reporting add-on and priority support.",
          "[01:02] Customer: Can you send that in writing before we decide?",
          "[01:15] Rep: Yes, I will send a summary today.",
        ].join("\n"),
      });
      const data = await bridge.call("bootstrap");
      state.sessions = data.sessions || [];
      renderSessionList();
      await selectSession(sessionId);
      showGlobalAlert(
        "Loaded an example call. It is sample text, labelled as such — replace it with your own transcript.",
        "info"
      );
    } catch (error) {
      notifyError(error, "Could not load the example");
    } finally {
      setBusy(false);
    }
  }

  async function boot() {
    ui.bootRetry.hidden = true;
    ui.bootMessage.textContent = "Opening your local workspace…";
    try {
      const data = await bridge.call("bootstrap");
      state.sessions = data.sessions || [];
      state.settings = data.settings || null;
      state.provider = data.provider || null;
      state.preview = data.preview || null;
      state.limits = Object.assign({}, DEFAULT_LIMITS, data.limits || {});
      const app = data.app || {};
      ui.railBuild.textContent = "CLEARCOMMIT TEAMS " + (app.version || "0.1.0");
      ui.statusDataDir.textContent = app.data_dir || "Local workspace";
      ui.statusDataDir.title = app.data_dir || "";
      renderProviderChip();
      renderSessionList();
      renderAssistantNotes();
      renderSignals(state.preview);
      try {
        await loadPlaybook();
      } catch (error) {
        notifyError(error, "Could not load the playbook");
      }
      if (state.sessions.length) await selectSession(state.sessions[0].id);
      else renderDesk();
      state.booted = true;
      ui.bootScreen.hidden = true;
      ui.appShell.hidden = false;
      setView("desk", { focus: false });
      updateNavBadges();
      const savedMode = readMode();
      if (savedMode) {
        applyMode(savedMode);
        if (savedMode === "company") setView("team", { focus: false });
      } else {
        applyMode("individual");
        openOnboarding();
      }
      if (
        state.provider &&
        state.provider.mode === "openai_compatible" &&
        !state.provider.configured
      ) {
        showGlobalAlert(
          "The configured provider is missing " +
            state.provider.missing.join(", ") +
            ". The demo coach still works.",
          "info"
        );
      }
    } catch (error) {
      ui.bootMessage.textContent = errorTitle(error) + ": " + describeError(error);
      ui.bootRetry.hidden = false;
    }
  }

  function handleAction(action) {
    switch (action) {
      case "open-settings":
        openSettings();
        break;
      case "new-session":
        openNewSession();
        break;
      case "open-import":
        openImport();
        break;
      case "save-to-cloud":
        void saveToCloud();
        break;
      case "load-example":
        void loadExampleConversation();
        break;
      case "open-add-line":
        openAddLine();
        break;
      case "select-all":
        selectFirstLines();
        break;
      case "clear-selection":
        clearSelection();
        break;
      case "analyze":
        void runAnalysis();
        break;
      case "goto-coach":
        setView("coach");
        break;
      case "goto-desk":
        setView("desk");
        break;
      case "approve-playbook":
        void approvePlaybook();
        break;
      case "refresh-playbook":
        void refreshPlaybook();
        break;
      case "refresh-signals":
        void refreshSignals();
        break;
      default:
        break;
    }
  }

  function init() {
    ui.bootRetry.addEventListener("click", function () {
      void boot();
    });
    document.querySelectorAll("[data-view]").forEach(function (button) {
      button.addEventListener("click", function () {
        setView(button.dataset.view);
      });
    });
    document.querySelectorAll("[data-action]").forEach(function (button) {
      button.addEventListener("click", function () {
        handleAction(button.dataset.action);
      });
    });
    document.querySelectorAll("[data-close-dialog]").forEach(function (button) {
      button.addEventListener("click", function () {
        const dialog = button.closest("dialog");
        if (dialog) closeDialog(dialog);
      });
    });
    document.querySelectorAll("dialog").forEach(function (dialog) {
      dialog.addEventListener("click", function (event) {
        if (event.target === dialog) closeDialog(dialog);
      });
    });
    document.querySelectorAll("[data-playbook-filter]").forEach(function (button) {
      button.addEventListener("click", function () {
        setPlaybookFilter(button.dataset.playbookFilter);
      });
    });
    ui.sessionFilter.addEventListener("input", function () {
      state.sessionFilter = ui.sessionFilter.value;
      renderSessionList();
    });
    ui.settingsForm.addEventListener("submit", function (event) {
      event.preventDefault();
      void persistSettings({ close: true, announce: true });
    });
    ui.testProvider.addEventListener("click", function () {
      void testProvider();
    });
    ui.newSessionForm.addEventListener("submit", function (event) {
      event.preventDefault();
      void createSessionFromDialog();
    });
    ui.importForm.addEventListener("submit", function (event) {
      event.preventDefault();
      void importTranscript();
    });
    ui.addLineForm.addEventListener("submit", function (event) {
      event.preventDefault();
      void addLine();
    });
    ui.playbookForm.addEventListener("submit", function (event) {
      void savePlaybookEntry(event);
    });
    ui.pbReset.addEventListener("click", function () {
      void resetPlaybook();
    });
    ui.askForm.addEventListener("submit", function (event) {
      void askAssistant(event);
    });
    ui.askQuestion.addEventListener("keydown", function (event) {
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
        event.preventDefault();
        if (!ui.askButton.disabled) void askAssistant();
      }
    });
    ui.lineSpeaker.addEventListener("change", function () {
      if (!state.session) return;
      ui.lineLanguage.value =
        ui.lineSpeaker.value === "rep"
          ? state.session.rep_language || "en"
          : state.session.customer_language || "en";
    });
    renderSelection();
    renderAssistantNotes();
    initOnboarding();
    void boot();
  }

  init();
})();
