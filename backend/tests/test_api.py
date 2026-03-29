import json
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from backend.server import create_server


class BackendApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.test_dir = Path(__file__).resolve().parent / ".tmp"
        cls.test_dir.mkdir(parents=True, exist_ok=True)
        db_path = str(cls.test_dir / "test.sqlite3")
        Path(db_path).unlink(missing_ok=True)
        cls.server = create_server("127.0.0.1", 0, db_path)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.05)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def request(self, method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url=f"http://127.0.0.1:{self.port}{path}",
            method=method,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def test_session_lifecycle_and_ingestion(self) -> None:
        status, created = self.request(
            "POST",
            "/sessions",
            {
                "user_id": "ryan",
                "course": "CMPSC 132",
                "assignment": "Linked List Homework",
                "planned_duration_minutes": 45,
            },
        )
        self.assertEqual(status, 201)
        session_id = created["session"]["session_id"]
        self.assertEqual(created["session"]["course"], "CMPSC 132")

        status, active = self.request("GET", "/sessions/active")
        self.assertEqual(status, 200)
        self.assertEqual(active["active_session"]["session_id"], session_id)

        status, listed = self.request("GET", "/sessions")
        self.assertEqual(status, 200)
        self.assertEqual(listed["sessions"][0]["session_id"], session_id)

        batch = {
            "batch_id": "batch_001",
            "session_id": session_id,
            "user_id": "ryan",
            "source": "chrome_extension",
            "extension_version": "0.1.0",
            "sent_at": "2026-03-28T20:14:35Z",
            "sequence_number": 1,
            "events": [
                {
                    "event_id": "evt_001",
                    "event_type": "browser_interval",
                    "session_id": session_id,
                    "user_id": "ryan",
                    "client_created_at": "2026-03-28T20:14:32Z",
                    "interval_start": "2026-03-28T20:14:02Z",
                    "interval_end": "2026-03-28T20:14:32Z",
                    "duration_ms": 30000,
                    "tab_id": 123,
                    "window_id": 9,
                    "tab_url": "https://docs.google.com/document/d/abc",
                    "tab_domain": "docs.google.com",
                    "tab_title": "Essay Draft - Google Docs",
                    "is_browser_focused": True,
                    "is_tab_active": True,
                    "page_visible": True,
                    "scroll_count": 18,
                    "click_count": 4,
                    "keystroke_count": 91,
                    "transition_in_reason": "tab_activated",
                    "transition_out_reason": "segment_rollover",
                    "segment_index": 6,
                    "is_partial_segment": False,
                    "extension_version": "0.1.0",
                    "collector_id": "chrome_ext_local",
                }
            ],
        }

        status, ingested = self.request("POST", "/telemetry/browser-batch", batch)
        self.assertEqual(status, 200)
        self.assertEqual(ingested["accepted_event_ids"], ["evt_001"])
        self.assertEqual(ingested["duplicate_event_ids"], [])

        status, duplicated = self.request("POST", "/telemetry/browser-batch", batch)
        self.assertEqual(status, 200)
        self.assertEqual(duplicated["accepted_event_ids"], [])
        self.assertEqual(duplicated["duplicate_event_ids"], ["evt_001"])

        status, debug_state = self.request("GET", "/debug/state")
        self.assertEqual(status, 200)
        self.assertEqual(debug_state["interval_count"], 1)
        self.assertEqual(debug_state["batch_count"], 1)

        status, session_detail = self.request("GET", f"/sessions/{session_id}")
        self.assertEqual(status, 200)
        self.assertEqual(session_detail["session"]["session_id"], session_id)

        status, session_intervals = self.request("GET", f"/sessions/{session_id}/intervals")
        self.assertEqual(status, 200)
        self.assertEqual(session_intervals["interval_count"], 1)
        self.assertEqual(session_intervals["intervals"][0]["event_id"], "evt_001")

        status, session_summary = self.request("GET", f"/sessions/{session_id}/summary")
        self.assertEqual(status, 200)
        self.assertEqual(session_summary["summary"]["interval_count"], 1)
        self.assertEqual(session_summary["summary"]["total_duration_ms"], 30000)

        status, stopped = self.request("POST", f"/sessions/{session_id}/stop")
        self.assertEqual(status, 200)
        self.assertEqual(stopped["session"]["status"], "stopped")


if __name__ == "__main__":
    unittest.main()
