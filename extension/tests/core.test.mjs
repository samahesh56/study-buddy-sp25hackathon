import assert from "node:assert/strict";

import {
  applyActivityDelta,
  buildBatch,
  closeInterval,
  createInterval,
  deriveDomain
} from "../core.js";

function run() {
  assert.equal(deriveDomain("https://www.docs.google.com/document/d/abc"), "docs.google.com");
  assert.equal(deriveDomain("notaurl"), null);

  const interval = createInterval({
    sessionId: "sess_1",
    userId: "ryan",
    tab: { id: 1, windowId: 2, url: "https://example.com", title: "Example" },
    transitionInReason: "session_started",
    segmentIndex: 0,
    startedAt: "2026-03-28T20:00:00.000Z"
  });

  const withClick = applyActivityDelta(interval, {
    click_count: 1,
    page_visible: true
  });
  assert.equal(withClick.click_count, 1);
  assert.equal(withClick.scroll_count, 0);
  assert.equal(withClick.page_visible, true);

  const withScrollBurst = applyActivityDelta(withClick, {
    scroll_count: 7,
    keystroke_count: 2
  });
  assert.equal(withScrollBurst.click_count, 1);
  assert.equal(withScrollBurst.scroll_count, 7);
  assert.equal(withScrollBurst.keystroke_count, 2);

  const closed = closeInterval(withScrollBurst, "click_activity", "2026-03-28T20:02:00.000Z");
  assert.equal(closed.duration_ms, 120000);
  assert.equal(closed.transition_out_reason, "click_activity");
  assert.equal(closed.click_count, 1);
  assert.equal(closed.scroll_count, 7);
  assert.equal(closed.keystroke_count, 2);

  const batch = buildBatch({
    sessionId: "sess_1",
    userId: "ryan",
    sequenceNumber: 4,
    events: [closed],
    sentAt: "2026-03-28T20:14:35.500Z"
  });
  assert.equal(batch.session_id, "sess_1");
  assert.equal(batch.sequence_number, 4);
  assert.equal(batch.events.length, 1);
  assert.equal(batch.events[0].transition_out_reason, "click_activity");

  console.log("extension core tests passed");
}

run();
