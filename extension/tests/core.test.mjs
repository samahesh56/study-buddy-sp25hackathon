import assert from "node:assert/strict";

import {
  buildBatch,
  closeInterval,
  createInterval,
  deriveDomain,
  segmentClosedInterval,
  shouldRollover,
  splitIntervalForRollover
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
  const closed = closeInterval(interval, "segment_rollover", "2026-03-28T20:00:30.000Z");
  assert.equal(closed.duration_ms, 30000);
  assert.equal(closed.transition_out_reason, "segment_rollover");

  assert.equal(shouldRollover(interval, "2026-03-28T20:00:29.999Z", 30000), false);
  assert.equal(shouldRollover(interval, "2026-03-28T20:00:30.000Z", 30000), true);

  const batch = buildBatch({
    sessionId: "sess_1",
    userId: "ryan",
    sequenceNumber: 4,
    events: [{ event_id: "evt_1" }],
    sentAt: "2026-03-28T20:14:35.500Z"
  });
  assert.equal(batch.session_id, "sess_1");
  assert.equal(batch.sequence_number, 4);
  assert.equal(batch.events.length, 1);

  const overshot = closeInterval(interval, "segment_rollover", "2026-03-28T20:00:53.670Z");
  overshot.scroll_count = 12;
  overshot.click_count = 4;
  overshot.keystroke_count = 10;
  const { closedSegment, remainingInterval } = splitIntervalForRollover(overshot, "2026-03-28T20:00:30.000Z");
  assert.equal(closedSegment.duration_ms, 30000);
  assert.equal(remainingInterval.interval_start, "2026-03-28T20:00:30.000Z");
  assert.equal(closedSegment.scroll_count + remainingInterval.scroll_count, 12);
  assert.equal(closedSegment.click_count + remainingInterval.click_count, 4);
  assert.equal(closedSegment.keystroke_count + remainingInterval.keystroke_count, 10);

  const overshotOnTabSwitch = closeInterval(interval, "tab_deactivated", "2026-03-28T20:01:07.000Z");
  overshotOnTabSwitch.scroll_count = 21;
  overshotOnTabSwitch.click_count = 5;
  overshotOnTabSwitch.keystroke_count = 9;
  const segmented = segmentClosedInterval(overshotOnTabSwitch, 30000);
  assert.equal(segmented.length, 3);
  assert.equal(segmented[0].duration_ms, 30000);
  assert.equal(segmented[0].transition_out_reason, "segment_rollover");
  assert.equal(segmented[1].duration_ms, 30000);
  assert.equal(segmented[1].transition_out_reason, "segment_rollover");
  assert.equal(segmented[2].duration_ms, 7000);
  assert.equal(segmented[2].transition_out_reason, "tab_deactivated");
  assert.equal(segmented.reduce((sum, item) => sum + item.scroll_count, 0), 21);
  assert.equal(segmented.reduce((sum, item) => sum + item.click_count, 0), 5);
  assert.equal(segmented.reduce((sum, item) => sum + item.keystroke_count, 0), 9);

  console.log("extension core tests passed");
}

run();
