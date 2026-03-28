export const MAX_SEGMENT_MS = 30_000;
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

export function shouldRollover(interval, currentTimeIso, maxSegmentMs = MAX_SEGMENT_MS) {
  if (!interval) {
    return false;
  }
  const elapsed = new Date(currentTimeIso).getTime() - new Date(interval.interval_start).getTime();
  return elapsed >= maxSegmentMs;
}

export function addMsToIso(isoString, msToAdd) {
  return new Date(new Date(isoString).getTime() + msToAdd).toISOString();
}

export function splitCounter(total, firstDurationMs, totalDurationMs) {
  if (!Number.isFinite(total) || total <= 0 || totalDurationMs <= 0) {
    return [0, Math.max(0, total || 0)];
  }
  const ratio = Math.min(1, Math.max(0, firstDurationMs / totalDurationMs));
  const firstValue = Math.min(total, Math.round(total * ratio));
  return [firstValue, total - firstValue];
}

export function splitIntervalForRollover(interval, rolloverAtIso) {
  const totalDurationMs = Math.max(
    0,
    new Date(interval.interval_end).getTime() - new Date(interval.interval_start).getTime()
  );
  const firstDurationMs = Math.max(
    0,
    new Date(rolloverAtIso).getTime() - new Date(interval.interval_start).getTime()
  );

  const [firstScroll, remainingScroll] = splitCounter(interval.scroll_count, firstDurationMs, totalDurationMs);
  const [firstClick, remainingClick] = splitCounter(interval.click_count, firstDurationMs, totalDurationMs);
  const [firstKeys, remainingKeys] = splitCounter(interval.keystroke_count, firstDurationMs, totalDurationMs);

  const closedSegment = {
    ...interval,
    interval_end: rolloverAtIso,
    duration_ms: firstDurationMs,
    scroll_count: firstScroll,
    click_count: firstClick,
    keystroke_count: firstKeys,
    transition_out_reason: "segment_rollover",
    is_partial_segment: false
  };

  const remainingInterval = {
    ...interval,
    event_id: newId("evt"),
    client_created_at: rolloverAtIso,
    interval_start: rolloverAtIso,
    duration_ms: totalDurationMs - firstDurationMs,
    scroll_count: remainingScroll,
    click_count: remainingClick,
    keystroke_count: remainingKeys,
    transition_in_reason: "segment_rollover",
    transition_out_reason: "",
    segment_index: interval.segment_index + 1
  };

  return { closedSegment, remainingInterval };
}

export function segmentClosedInterval(interval, maxSegmentMs = MAX_SEGMENT_MS) {
  const segments = [];
  let workingInterval = { ...interval };

  while (workingInterval.duration_ms > maxSegmentMs) {
    const rolloverAtIso = addMsToIso(workingInterval.interval_start, maxSegmentMs);
    const { closedSegment, remainingInterval } = splitIntervalForRollover(workingInterval, rolloverAtIso);
    segments.push(closedSegment);
    workingInterval = {
      ...remainingInterval,
      transition_out_reason: interval.transition_out_reason,
      is_partial_segment: interval.is_partial_segment
    };
  }

  segments.push(workingInterval);
  return segments;
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
