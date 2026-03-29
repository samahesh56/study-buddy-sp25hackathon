export const QUEUE_FLUSH_THRESHOLD = 20;

export function nowIso(date = new Date()) {
  return date.toISOString();
}

export function deriveDomain(urlString) {
  if (!urlString) {
    return null;
  }

  try {
    return new URL(urlString).hostname.replace(/^www\./, "").toLowerCase();
  } catch {
    return null;
  }
}

export function newId(prefix) {
  const cryptoObj = globalThis.crypto;
  if (cryptoObj?.randomUUID) {
    return `${prefix}_${cryptoObj.randomUUID().replace(/-/g, "").slice(0, 12)}`;
  }
  return `${prefix}_${Math.random().toString(16).slice(2, 14)}`;
}

export function createInterval({ sessionId, userId, tab, transitionInReason, segmentIndex, startedAt }) {
  const startIso = startedAt ?? nowIso();
  return {
    event_id: newId("evt"),
    event_type: "browser_interval",
    session_id: sessionId,
    user_id: userId ?? null,
    client_created_at: startIso,
    interval_start: startIso,
    interval_end: startIso,
    duration_ms: 0,
    tab_id: tab?.id ?? null,
    window_id: tab?.windowId ?? null,
    tab_url: tab?.url ?? null,
    tab_domain: deriveDomain(tab?.url),
    tab_title: tab?.title ?? null,
    is_browser_focused: true,
    is_tab_active: true,
    page_visible: true,
    scroll_count: 0,
    click_count: 0,
    keystroke_count: 0,
    transition_in_reason: transitionInReason,
    transition_out_reason: "",
    segment_index: segmentIndex,
    is_partial_segment: false,
    extension_version: "0.1.0",
    collector_id: "studyclaw_chrome_ext"
  };
}

export function closeInterval(interval, transitionOutReason, endedAt, isPartialSegment = false) {
  const endIso = endedAt ?? nowIso();
  const durationMs = Math.max(0, new Date(endIso).getTime() - new Date(interval.interval_start).getTime());
  return {
    ...interval,
    interval_end: endIso,
    duration_ms: durationMs,
    transition_out_reason: transitionOutReason,
    is_partial_segment: isPartialSegment
  };
}

export function applyActivityDelta(interval, delta = {}) {
  return {
    ...interval,
    scroll_count: interval.scroll_count + (delta.scroll_count ?? 0),
    click_count: interval.click_count + (delta.click_count ?? 0),
    keystroke_count: interval.keystroke_count + (delta.keystroke_count ?? 0),
    page_visible: delta.page_visible ?? interval.page_visible
  };
}

export function buildBatch({ sessionId, userId, sequenceNumber, events, sentAt }) {
  return {
    batch_id: newId("batch"),
    session_id: sessionId,
    user_id: userId ?? null,
    source: "chrome_extension",
    extension_version: "0.1.0",
    sent_at: sentAt ?? nowIso(),
    sequence_number: sequenceNumber,
    events
  };
}
