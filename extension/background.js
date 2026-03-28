import {
  addMsToIso,
  MAX_SEGMENT_MS,
  QUEUE_FLUSH_THRESHOLD,
  buildBatch,
  closeInterval,
  createInterval,
  nowIso,
  splitIntervalForRollover,
  shouldRollover
} from "./core.js";

const STORAGE_KEYS = {
  backendBaseUrl: "backendBaseUrl",
  activeSession: "activeSession",
  currentInterval: "currentInterval",
  queuedEvents: "queuedEvents",
  batchSequence: "batchSequence",
  lastUploadResult: "lastUploadResult",
  lastError: "lastError"
};

const ALARMS = {
  sessionSync: "studyclaw-session-sync",
  flushQueue: "studyclaw-flush-queue",
  rollover: "studyclaw-rollover"
};

async function getState(keys) {
  return chrome.storage.local.get(keys);
}

async function setState(values) {
  await chrome.storage.local.set(values);
}

async function ensureDefaults() {
  const state = await getState(Object.values(STORAGE_KEYS));
  const updates = {};
  if (!state[STORAGE_KEYS.backendBaseUrl]) {
    updates[STORAGE_KEYS.backendBaseUrl] = "http://127.0.0.1:8000";
  }
  if (!state[STORAGE_KEYS.queuedEvents]) {
    updates[STORAGE_KEYS.queuedEvents] = [];
  }
  if (typeof state[STORAGE_KEYS.batchSequence] !== "number") {
    updates[STORAGE_KEYS.batchSequence] = 0;
  }
  if (Object.keys(updates).length > 0) {
    await setState(updates);
  }
}

async function setLastError(message) {
  await setState({ [STORAGE_KEYS.lastError]: { message, at: nowIso() } });
}

async function clearLastError() {
  await chrome.storage.local.remove(STORAGE_KEYS.lastError);
}

async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  return tabs[0] ?? null;
}

async function getBackendBaseUrl() {
  const state = await getState([STORAGE_KEYS.backendBaseUrl]);
  return state[STORAGE_KEYS.backendBaseUrl] || "http://127.0.0.1:8000";
}

async function getActiveSession() {
  const state = await getState([STORAGE_KEYS.activeSession]);
  return state[STORAGE_KEYS.activeSession] ?? null;
}

async function setActiveSession(session) {
  await setState({ [STORAGE_KEYS.activeSession]: session });
}

async function getCurrentInterval() {
  const state = await getState([STORAGE_KEYS.currentInterval]);
  return state[STORAGE_KEYS.currentInterval] ?? null;
}

async function setCurrentInterval(interval) {
  await setState({ [STORAGE_KEYS.currentInterval]: interval });
}

async function getQueue() {
  const state = await getState([STORAGE_KEYS.queuedEvents]);
  return state[STORAGE_KEYS.queuedEvents] ?? [];
}

async function setQueue(queue) {
  await setState({ [STORAGE_KEYS.queuedEvents]: queue });
}

async function appendToQueue(event) {
  const queue = await getQueue();
  queue.push(event);
  await setQueue(queue);
  if (queue.length >= QUEUE_FLUSH_THRESHOLD) {
    await flushQueue();
  }
}

async function incrementCounters(tabId, delta) {
  if (typeof tabId !== "number") {
    return;
  }

  const current = await getCurrentInterval();
  if (!current || current.tab_id !== tabId) {
    return;
  }

  current.scroll_count += delta.scroll_count ?? 0;
  current.click_count += delta.click_count ?? 0;
  current.keystroke_count += delta.keystroke_count ?? 0;
  current.page_visible = delta.page_visible ?? current.page_visible;
  await setCurrentInterval(current);
}

async function openInterval(reason, tabOverride = null) {
  const session = await getActiveSession();
  if (!session) {
    return;
  }

  const tab = tabOverride ?? (await getActiveTab());
  if (!tab?.id) {
    return;
  }

  const current = await getCurrentInterval();
  const nextIndex = (current?.segment_index ?? -1) + 1;
  const interval = createInterval({
    sessionId: session.session_id,
    userId: session.user_id,
    tab,
    transitionInReason: reason,
    segmentIndex: nextIndex,
    startedAt: nowIso()
  });
  await setCurrentInterval(interval);
}

async function closeCurrentInterval(reason, options = {}) {
  const current = await getCurrentInterval();
  if (!current) {
    return null;
  }

  const closed = closeInterval(current, reason, nowIso(), Boolean(options.isPartialSegment));
  await appendToQueue(closed);
  await setCurrentInterval(null);
  return closed;
}

async function rolloverCurrentInterval() {
  const current = await getCurrentInterval();
  if (!current) {
    return;
  }
  const rolloverCheckAt = nowIso();
  if (!shouldRollover(current, rolloverCheckAt, MAX_SEGMENT_MS)) {
    return;
  }

  let workingInterval = closeInterval(current, "segment_rollover", rolloverCheckAt, false);
  while (workingInterval.duration_ms >= MAX_SEGMENT_MS) {
    const rolloverAtIso = addMsToIso(workingInterval.interval_start, MAX_SEGMENT_MS);
    const { closedSegment, remainingInterval } = splitIntervalForRollover(workingInterval, rolloverAtIso);
    await appendToQueue(closedSegment);
    workingInterval = remainingInterval;
  }

  workingInterval.transition_out_reason = "";
  workingInterval.duration_ms = 0;
  workingInterval.interval_end = workingInterval.interval_start;
  await setCurrentInterval(workingInterval);
}

async function transitionToTab(reason, tabId) {
  const session = await getActiveSession();
  if (!session) {
    return;
  }

  const tab = tabId ? await chrome.tabs.get(tabId).catch(() => null) : await getActiveTab();
  if (!tab?.id) {
    return;
  }

  const current = await getCurrentInterval();
  if (current?.tab_id === tab.id && current.tab_url === (tab.url ?? null) && current.tab_title === (tab.title ?? null)) {
    return;
  }

  if (current) {
    await closeCurrentInterval(reason === "navigation_completed" ? "navigation_completed" : "tab_deactivated");
  }
  await openInterval(reason, tab);
}

async function onBrowserBlur() {
  await closeCurrentInterval("window_blurred");
}

async function onBrowserFocus() {
  const session = await getActiveSession();
  if (!session) {
    return;
  }
  const current = await getCurrentInterval();
  if (!current) {
    await openInterval("window_focused");
  }
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    }
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${text}`);
  }
  return response.json();
}

async function syncSessionFromBackend() {
  const backendBaseUrl = await getBackendBaseUrl();
  try {
    const payload = await fetchJson(`${backendBaseUrl}/sessions/active`);
    const serverSession = payload.active_session ?? null;
    const currentSession = await getActiveSession();

    if (!serverSession && currentSession) {
      await closeCurrentInterval("session_stopped", { isPartialSegment: true });
      await flushQueue();
      await setActiveSession(null);
      return;
    }

    if (serverSession && (!currentSession || currentSession.session_id !== serverSession.session_id)) {
      await setActiveSession(serverSession);
      await openInterval("session_started");
    }

    await clearLastError();
  } catch (error) {
    await setLastError(`Session sync failed: ${error.message}`);
  }
}

async function flushQueue() {
  const queue = await getQueue();
  if (queue.length === 0) {
    return;
  }

  const session = await getActiveSession();
  const queueSessionId = queue[0]?.session_id;
  const queueUserId = queue[0]?.user_id ?? null;
  const effectiveSessionId = session?.session_id ?? queueSessionId;
  const effectiveUserId = session?.user_id ?? queueUserId;
  if (!effectiveSessionId) {
    return;
  }

  const state = await getState([STORAGE_KEYS.batchSequence]);
  const nextSequence = (state[STORAGE_KEYS.batchSequence] ?? 0) + 1;
  const batch = buildBatch({
    sessionId: effectiveSessionId,
    userId: effectiveUserId,
    sequenceNumber: nextSequence,
    events: queue,
    sentAt: nowIso()
  });

  const backendBaseUrl = await getBackendBaseUrl();
  try {
    const response = await fetchJson(`${backendBaseUrl}/telemetry/browser-batch`, {
      method: "POST",
      body: JSON.stringify(batch)
    });
    const accepted = new Set([...(response.accepted_event_ids ?? []), ...(response.duplicate_event_ids ?? [])]);
    const remaining = queue.filter((event) => !accepted.has(event.event_id));
    await setState({
      [STORAGE_KEYS.queuedEvents]: remaining,
      [STORAGE_KEYS.batchSequence]: nextSequence,
      [STORAGE_KEYS.lastUploadResult]: {
        batch_id: response.batch_id,
        accepted_count: response.accepted_event_ids?.length ?? 0,
        duplicate_count: response.duplicate_event_ids?.length ?? 0,
        at: response.server_received_at
      }
    });
    await clearLastError();
  } catch (error) {
    await setLastError(`Upload failed: ${error.message}`);
  }
}

async function startSession(userId) {
  const backendBaseUrl = await getBackendBaseUrl();
  const payload = await fetchJson(`${backendBaseUrl}/sessions`, {
    method: "POST",
    body: JSON.stringify({ user_id: userId || null })
  });
  await setActiveSession(payload.session);
  await openInterval("session_started");
}

async function stopSession() {
  const session = await getActiveSession();
  if (!session) {
    return;
  }

  const backendBaseUrl = await getBackendBaseUrl();
  await closeCurrentInterval("session_stopped", { isPartialSegment: true });
  await flushQueue();
  await fetchJson(`${backendBaseUrl}/sessions/${session.session_id}/stop`, {
    method: "POST",
    body: JSON.stringify({})
  });
  await setActiveSession(null);
  await clearLastError();
}

chrome.runtime.onInstalled.addListener(async () => {
  await ensureDefaults();
  chrome.alarms.create(ALARMS.sessionSync, { periodInMinutes: 0.5 });
  chrome.alarms.create(ALARMS.flushQueue, { periodInMinutes: 0.5 });
  chrome.alarms.create(ALARMS.rollover, { periodInMinutes: 0.5 });
  await syncSessionFromBackend();
});

chrome.runtime.onStartup.addListener(async () => {
  await ensureDefaults();
  chrome.alarms.create(ALARMS.sessionSync, { periodInMinutes: 0.5 });
  chrome.alarms.create(ALARMS.flushQueue, { periodInMinutes: 0.5 });
  chrome.alarms.create(ALARMS.rollover, { periodInMinutes: 0.5 });
  await syncSessionFromBackend();
  await flushQueue();
});

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === ALARMS.sessionSync) {
    await syncSessionFromBackend();
  } else if (alarm.name === ALARMS.flushQueue) {
    await flushQueue();
  } else if (alarm.name === ALARMS.rollover) {
    await rolloverCurrentInterval();
  }
});

chrome.tabs.onActivated.addListener(async ({ tabId }) => {
  await transitionToTab("tab_activated", tabId);
});

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (!changeInfo.url && changeInfo.status !== "complete" && !changeInfo.title) {
    return;
  }
  if (!tab.active) {
    return;
  }
  await transitionToTab("navigation_completed", tabId);
});

chrome.windows.onFocusChanged.addListener(async (windowId) => {
  if (windowId === chrome.windows.WINDOW_ID_NONE) {
    await onBrowserBlur();
  } else {
    await onBrowserFocus();
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === "content-activity") {
    incrementCounters(sender.tab?.id, message.payload || {})
      .then(() => sendResponse({ ok: true }))
      .catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }

  if (message?.type === "popup:get-state") {
    Promise.all([getState(Object.values(STORAGE_KEYS)), getActiveTab()]).then(([state, activeTab]) => {
      sendResponse({
        backendBaseUrl: state[STORAGE_KEYS.backendBaseUrl],
        activeSession: state[STORAGE_KEYS.activeSession] ?? null,
        currentInterval: state[STORAGE_KEYS.currentInterval] ?? null,
        queuedEventCount: (state[STORAGE_KEYS.queuedEvents] ?? []).length,
        lastUploadResult: state[STORAGE_KEYS.lastUploadResult] ?? null,
        lastError: state[STORAGE_KEYS.lastError] ?? null,
        activeTab: activeTab
          ? {
              id: activeTab.id,
              title: activeTab.title,
              url: activeTab.url
            }
          : null
      });
    });
    return true;
  }

  if (message?.type === "popup:set-backend-url") {
    setState({ [STORAGE_KEYS.backendBaseUrl]: message.backendBaseUrl }).then(() => sendResponse({ ok: true }));
    return true;
  }

  if (message?.type === "popup:start-session") {
    startSession(message.userId)
      .then(() => sendResponse({ ok: true }))
      .catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }

  if (message?.type === "popup:stop-session") {
    stopSession()
      .then(() => sendResponse({ ok: true }))
      .catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }

  if (message?.type === "popup:sync-session") {
    syncSessionFromBackend()
      .then(() => sendResponse({ ok: true }))
      .catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }

  if (message?.type === "popup:flush-queue") {
    flushQueue()
      .then(() => sendResponse({ ok: true }))
      .catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }

  return false;
});
