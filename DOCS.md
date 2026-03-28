# StudyClaw Docs

This document describes the current StudyClaw raw telemetry implementation and should be kept up to date as the project evolves.

## Current Scope

The current implementation is the first end-to-end raw telemetry slice of StudyClaw:

- a Python backend
- a Chrome Manifest V3 extension
- session creation and stopping
- raw browser interval collection
- raw telemetry batch ingestion
- server-side timestamping
- raw storage in SQLite
- per-session inspection routes

This is intentionally limited to browser telemetry only. There is no relevance scoring, analytics pipeline, screenshot capture, camera input, or OpenClaw handoff yet.

## Current Architecture

The current system has two runtime pieces.

1. Python backend
- creates sessions
- assigns unique session IDs
- receives telemetry batches
- validates telemetry payloads
- timestamps receipt on the server
- stores raw intervals and batch metadata
- exposes session-specific retrieval routes

2. Chrome extension
- starts and stops sessions through the backend
- tracks the active browser tab context
- collects raw interaction counts
- closes intervals on context changes
- rolls long intervals every 30 seconds
- enforces exact 30-second segmentation on all close paths
- queues closed intervals locally
- uploads telemetry batches to the backend

## Project Layout

- [backend](C:/Users/ryanf/coding/hackpsu/backend)
- [extension](C:/Users/ryanf/coding/hackpsu/extension)
- [README.md](C:/Users/ryanf/coding/hackpsu/README.md)
- [DOCS.md](C:/Users/ryanf/coding/hackpsu/DOCS.md)
- [raw-data.example.json](C:/Users/ryanf/coding/hackpsu/raw-data.example.json)

Important files:

- [backend/server.py](C:/Users/ryanf/coding/hackpsu/backend/server.py)
- [backend/storage.py](C:/Users/ryanf/coding/hackpsu/backend/storage.py)
- [backend/tests/test_api.py](C:/Users/ryanf/coding/hackpsu/backend/tests/test_api.py)
- [extension/manifest.json](C:/Users/ryanf/coding/hackpsu/extension/manifest.json)
- [extension/background.js](C:/Users/ryanf/coding/hackpsu/extension/background.js)
- [extension/core.js](C:/Users/ryanf/coding/hackpsu/extension/core.js)
- [extension/content.js](C:/Users/ryanf/coding/hackpsu/extension/content.js)
- [extension/popup.html](C:/Users/ryanf/coding/hackpsu/extension/popup.html)
- [extension/popup.js](C:/Users/ryanf/coding/hackpsu/extension/popup.js)

## Backend Behavior

The backend currently exposes these routes:

- `GET /health`
- `POST /sessions`
- `GET /sessions/active`
- `GET /sessions?session_id=...`
- `GET /sessions/{id}`
- `GET /sessions/{id}/intervals`
- `GET /sessions/{id}/summary`
- `POST /sessions/{id}/stop`
- `POST /telemetry/browser-batch`
- `GET /debug/state`

### Session Behavior

`POST /sessions` creates a new active session and returns a unique `session_id`.

Current behavior:

- one session is treated as active at a time
- creating a new session stops any previously active session
- stopping a session marks it as `stopped`
- telemetry can still arrive for a just-stopped session because ingestion is keyed by `session_id`, not only current active state

### Raw Storage

SQLite storage is created under:

- [backend/data/studyclaw.sqlite3](C:/Users/ryanf/coding/hackpsu/backend/data/studyclaw.sqlite3)

Current tables:

- `sessions`
- `telemetry_batches`
- `browser_intervals_raw`

Current storage hardening:

- WAL mode enabled
- busy timeout enabled
- indexes for session lookup and interval retrieval

The backend stores:

- original raw event JSON
- original raw batch JSON
- server receipt timestamp
- normalized domain

The backend also supports clean per-session retrieval so a single session can be inspected without mixing multiple runs together.

## Extension Behavior

The extension currently implements the agreed raw collection rules.

### Collection Unit

The primary collection unit is a closed `browser_interval`.

An interval is opened when:

- a session starts
- the active tab changes
- the browser regains focus
- navigation completes into a new active page
- a previous segment rolls over

An interval is closed when:

- the active tab changes
- navigation changes the current page context
- the browser loses focus
- the session stops
- a 30-second max segment is reached

### Interaction Counts

The content script sends lightweight counters to the background worker:

- `scroll_count`
- `click_count`
- `keystroke_count`
- `page_visible`

These are attached to the currently open interval for the active tab.

### Upload Behavior

The extension uploads closed intervals in batches.

Current rules:

- max interval segment length: `30 seconds`
- batch flush threshold: `20 events`
- periodic alarm-driven sync/flush cadence: `30 seconds`
- immediate flush on session stop

The extension keeps queued intervals locally until the backend acknowledges them.

Important implementation detail:

- Chrome MV3 alarms are coarse, so the service worker may wake up after the 30-second boundary
- the extension corrects that by splitting overshot intervals into exact 30-second stored segments plus a carried-forward remainder
- that split now happens both on periodic rollover checks and on all other close reasons such as tab switch, blur, and session stop
- this keeps stored raw interval durations aligned with the intended segmentation rule

Additional reliability behavior:

- queued events can still flush after browser restart if the local active session state is missing but queued raw events still exist
- extension startup performs a backend session sync and a queue flush attempt

## Raw Event Shape

The main raw event type is `browser_interval`.

Important fields:

- `event_id`
- `event_type`
- `session_id`
- `user_id`
- `client_created_at`
- `interval_start`
- `interval_end`
- `duration_ms`
- `tab_id`
- `window_id`
- `tab_url`
- `tab_domain`
- `tab_title`
- `is_browser_focused`
- `is_tab_active`
- `page_visible`
- `scroll_count`
- `click_count`
- `keystroke_count`
- `transition_in_reason`
- `transition_out_reason`
- `segment_index`
- `is_partial_segment`
- `extension_version`
- `collector_id`

The extension sends those inside a batch payload that also includes:

- `batch_id`
- `session_id`
- `user_id`
- `source`
- `extension_version`
- `sent_at`
- `sequence_number`
- `events`

For a team-facing example payload, use [raw-data.example.json](C:/Users/ryanf/coding/hackpsu/raw-data.example.json).

## How To Run The Backend

From the repo root:

```bash
python -m backend.server
```

Expected startup behavior:

- the backend listens on `http://127.0.0.1:8000`
- SQLite data is created under `backend/data/`

Health check:

```text
http://127.0.0.1:8000/health
```

Expected response:

```json
{
  "status": "ok",
  "server_time": "..."
}
```

## How To Load The Extension

1. Open Chrome
2. Go to `chrome://extensions`
3. Enable Developer mode
4. Click `Load unpacked`
5. Select [extension](C:/Users/ryanf/coding/hackpsu/extension)
6. Pin the extension if you want easier access
7. Open the extension popup
8. Confirm Backend URL is `http://127.0.0.1:8000`

## How To Start And Stop A Session

In the popup:

1. Enter a user ID such as `ryan`
2. Click `Start Session`
3. Browse normally
4. Click `Stop Session` when done

The popup should show:

- `activeSession`
- current `session_id`
- `currentInterval`
- `queuedEventCount`
- `lastUploadResult`
- `lastError` if something failed

## Manual End-To-End Test

Use this exact flow for a basic verification pass.

### Step 1: Start services

1. Run the backend:

```bash
python -m backend.server
```

2. Load or reload the extension in Chrome
3. Open the popup
4. Set backend URL to `http://127.0.0.1:8000`

### Step 2: Start a session

1. Enter a user ID
2. Click `Start Session`

Expected result:

- popup shows a non-null `activeSession`
- popup shows a `session_id`
- popup shows a non-null `currentInterval`

### Step 3: Generate telemetry

1. Open one normal website such as Reddit, GitHub, or Wikipedia
2. Stay there for 40 to 45 seconds
3. Scroll or interact a bit while on that page
4. Switch to another normal website
5. Stay there for 10 to 15 seconds
6. Click `Stop Session`

### Step 4: Inspect backend state

Open:

```text
http://127.0.0.1:8000/debug/state
```

Expected result:

- `batch_count` is greater than `0`
- `interval_count` is greater than `0`
- `recent_intervals` contains your visited domains and titles
- at least one interval should show non-zero interaction counts if you clicked or scrolled
- if you stayed on a page longer than 30 seconds, you should see a rollover-created interval boundary

For a clean single-session artifact, prefer:

```text
http://127.0.0.1:8000/sessions/{session_id}/intervals
```

For a compact per-session rollup, use:

```text
http://127.0.0.1:8000/sessions/{session_id}/summary
```

## What "Working" Looks Like

The current system is working if all of these are true:

- backend health endpoint responds
- popup can start a session successfully
- popup shows an active session and current interval
- browsing creates queued intervals
- batches upload successfully
- `/debug/state` shows stored raw intervals
- stored titles and domains roughly match what you visited
- interaction counters are non-zero on pages where you interacted
- `/sessions/{id}/intervals` returns only the intervals for the chosen session

## Troubleshooting

If nothing is arriving in `/debug/state`, check these in order.

1. Confirm backend is running
- open `http://127.0.0.1:8000/health`

2. Confirm the popup backend URL is correct
- it should be `http://127.0.0.1:8000`

3. Check popup state
- `activeSession` should not be null after starting
- `lastError` should be empty or null

4. Check Chrome extension internals
- go to `chrome://extensions`
- find the StudyClaw extension
- open the service worker inspector / background console
- look for network or runtime errors

5. Check backend debug state
- `GET /sessions/active`
- `GET /debug/state`
- `GET /sessions/{id}/intervals`

## Current Automated Tests

Backend API test:

```bash
python -m unittest backend.tests.test_api
```

Extension core logic test:

```bash
node extension/tests/core.test.mjs
```

Current automated coverage includes:

- session create / active / stop flow
- telemetry ingestion
- deduplication by `event_id`
- session detail retrieval
- session interval retrieval
- session summary retrieval
- interval duration calculation
- domain parsing
- rollover rule
- batch builder behavior

Current automated coverage does not include:

- real Chrome browser integration
- real service worker lifecycle behavior
- real content script to background messaging inside Chrome

Those still require manual browser testing.

## Production Status

This is production-oriented for the current Phase 1 raw telemetry slice, not a claim that the entire StudyClaw platform is complete.

What is solid for this phase:

- session lifecycle
- raw interval collection
- batching
- backend receipt
- server-side timestamping
- deduplication
- per-session retrieval
- shareable raw data artifact

What is still not implemented:

- authentication and user authorization
- analytics and scoring
- narrative compression
- screenshot collection
- camera attention tracking
- OpenClaw / StudyClaw coaching layer
- Base44 integration
- operational monitoring and deployment hardening

## Team Handoff Artifact

Use [raw-data.example.json](C:/Users/ryanf/coding/hackpsu/raw-data.example.json) when sharing the Phase 1 raw telemetry schema with the team.

It contains:

- a valid example batch payload
- sample interval records
- field-by-field descriptions for every currently collected raw metric

## Update Policy For This File

When the project changes, update this file to reflect:

- new routes
- new schema fields
- new runtime pieces
- changed setup steps
- changed test steps
- new limitations or removed limitations

This file should remain the main human-readable source of truth for how the current StudyClaw implementation actually works.
