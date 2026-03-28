# study-buddy-sp25hackathon

StudyClaw raw telemetry MVP:

- `backend/`: minimal Python backend for session lifecycle and raw browser telemetry ingestion
- `extension/`: Chrome Manifest V3 extension for active-tab interval collection and batch uploads

## Run the backend

```bash
python -m backend.server
```

Default backend URL: `http://127.0.0.1:8000`

Key endpoints:

- `POST /sessions`
- `GET /sessions/active`
- `GET /sessions/{id}`
- `GET /sessions/{id}/intervals`
- `GET /sessions/{id}/summary`
- `POST /sessions/{id}/stop`
- `POST /telemetry/browser-batch`
- `GET /debug/state`

## Run backend tests

```bash
python -m unittest backend.tests.test_api
```

## Run extension logic tests

```bash
node extension/tests/core.test.mjs
```

## Load the extension

1. Open Chrome extensions page: `chrome://extensions`
2. Enable Developer mode
3. Click `Load unpacked`
4. Select the `extension/` directory
5. Open the popup and confirm the backend URL is `http://127.0.0.1:8000`
6. Start a session from the popup
7. Browse a few tabs, then stop the session
8. Inspect `http://127.0.0.1:8000/debug/state`

For fuller setup and testing instructions, see `DOCS.md`.
