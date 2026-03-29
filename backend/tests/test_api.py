import json
import csv
import os
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from backend.cv_manager import ComputerVisionManager
from backend.server import create_server
from backend.storage import Storage


class BackendApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.previous_chat_mode = os.environ.get("STUDYCLAW_CHAT_MODE")
        os.environ["STUDYCLAW_CHAT_MODE"] = "placeholder"
        cls.test_dir = Path(__file__).resolve().parent / ".tmp"
        cls.test_dir.mkdir(parents=True, exist_ok=True)
        db_path = str(cls.test_dir / "test.sqlite3")
        Path(db_path).unlink(missing_ok=True)
        cls.camera_data_dir = cls.test_dir / "camera-data"
        cls.fake_cv_script = cls._write_fake_cv_script(cls.test_dir / "fake_cv_process.py")
        cls._write_camera_fixture(cls.camera_data_dir)
        cls.server = create_server("127.0.0.1", 0, db_path, str(cls.camera_data_dir), str(cls.fake_cv_script))
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.05)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        if cls.previous_chat_mode is None:
            os.environ.pop("STUDYCLAW_CHAT_MODE", None)
        else:
            os.environ["STUDYCLAW_CHAT_MODE"] = cls.previous_chat_mode

    @classmethod
    def _write_camera_fixture(cls, camera_data_dir: Path) -> None:
        session_dir = camera_data_dir / "Session 1 - 03-28-26"
        session_dir.mkdir(parents=True, exist_ok=True)
        sid = "2026-03-28T20-14-00Z"

        transitions = {
            "started_at": "2026-03-28T20:14:00Z",
            "ended_at": "2026-03-28T20:14:40Z",
            "duration_sec": 40.0,
            "total_frames": 1200,
            "average_fps": 30.0,
            "total_blinks": 4,
            "state_summary": {
                "FOCUSED": {"frames": 900, "seconds": 30.0, "percent": 75.0},
                "SEMI_FOCUSED": {"frames": 180, "seconds": 6.0, "percent": 15.0},
                "AWAY": {"frames": 120, "seconds": 4.0, "percent": 10.0},
            },
            "distracted_snap_count": 1,
            "transitions": [
                {"from_state": "FOCUSED", "to": "AWAY", "at_sec": 31.0, "duration_sec": 31.0},
                {"from_state": "AWAY", "to": "FOCUSED", "at_sec": 35.0, "duration_sec": 4.0},
            ],
        }
        (session_dir / f"{sid}_transitions.json").write_text(json.dumps(transitions), encoding="utf-8")

        snapshots = {
            "started_at": "2026-03-28T20:14:00Z",
            "session_id": sid,
            "snapshots": [
                {
                    "timestamp": "2026-03-28T20:14:05Z",
                    "elapsed_sec": 5,
                    "state": "FOCUSED",
                    "phone_detected": False,
                    "gaze_away": False,
                    "ear": 0.31,
                    "blink_count": 1,
                    "yaw": 2.0,
                    "pitch": 1.5,
                    "roll": 0.3,
                    "focus_score": 82.0,
                    "focus_label": "Focused",
                }
            ],
        }
        (session_dir / f"{sid}_snapshots.json").write_text(json.dumps(snapshots), encoding="utf-8")

        with (session_dir / f"{sid}_windows.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "timestamp", "window_length_sec", "face_present", "face_present_percent",
                    "face_missing_seconds", "longest_face_missing_seconds", "looking_forward_percent",
                    "longest_forward_streak_seconds", "lookaway_events", "blink_count",
                    "avg_blink_duration_sec", "long_eye_closure_count", "eye_closed_percent",
                    "head_motion_score", "motion_burst_count", "avg_face_area_percent",
                    "looking_down_percent", "near_face_motion_percent", "desk_motion_percent",
                    "phone_candidate_percent", "writing_candidate_percent",
                    "longest_phone_streak_seconds", "longest_writing_streak_seconds",
                    "likely_phone_use", "likely_writing", "camera_focus_score",
                    "camera_focus_label", "attention_state",
                ]
            )
            writer.writerow(
                [
                    "2026-03-28T20:14:10Z", 5, True, 100.0, 0.0, 0.0, 88.0, 4.0, 0, 1, 0.1, 0,
                    2.0, 0.05, 0, 7.5, 3.0, 2.0, 1.0, 0.0, 0.0, 0.0, 0.0, False, False,
                    84.0, "Focused", "FOCUSED",
                ]
            )
            writer.writerow(
                [
                    "2026-03-28T20:14:15Z", 5, True, 100.0, 0.0, 0.0, 81.0, 3.5, 1, 1, 0.1, 0,
                    3.0, 0.10, 0, 7.3, 8.0, 3.0, 2.0, 0.0, 0.0, 0.0, 0.0, False, False,
                    79.0, "Focused", "FOCUSED",
                ]
            )

        (session_dir / f"{sid}_summary.png").write_bytes(b"\x89PNG\r\n\x1a\nfakepng")
        distracted_dir = session_dir / "distracted"
        distracted_dir.mkdir(exist_ok=True)
        (distracted_dir / "2026-03-28T20-14-12_distracted.png").write_bytes(b"\x89PNG\r\n\x1a\nsnap")

    @classmethod
    def _write_fake_cv_script(cls, script_path: Path) -> Path:
        script_path.write_text(
            "\n".join(
                [
                    "import os",
                    "import signal",
                    "import time",
                    "from pathlib import Path",
                    "",
                    "stop_requested = False",
                    "ready_file = os.environ.get('STUDYCLAW_CV_READY_FILE')",
                    "",
                    "def request_stop(_signum=None, _frame=None):",
                    "    global stop_requested",
                    "    stop_requested = True",
                    "",
                    "signal.signal(signal.SIGINT, request_stop)",
                    "if hasattr(signal, 'SIGTERM'):",
                    "    signal.signal(signal.SIGTERM, request_stop)",
                    "if hasattr(signal, 'SIGBREAK'):",
                    "    signal.signal(signal.SIGBREAK, request_stop)",
                    "",
                    "if ready_file:",
                    "    Path(ready_file).write_text('ready\\n', encoding='utf-8')",
                    "",
                    "while not stop_requested:",
                    "    time.sleep(0.1)",
                ]
            ),
            encoding="utf-8",
        )
        return script_path

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

    def request_text(self, method: str, path: str) -> tuple[int, str, dict]:
        request = urllib.request.Request(
            url=f"http://127.0.0.1:{self.port}{path}",
            method=method,
        )
        with urllib.request.urlopen(request) as response:
            return response.status, response.read().decode("utf-8"), dict(response.headers.items())

    def request_bytes(self, method: str, path: str) -> tuple[int, bytes, dict]:
        request = urllib.request.Request(
            url=f"http://127.0.0.1:{self.port}{path}",
            method=method,
        )
        with urllib.request.urlopen(request) as response:
            return response.status, response.read(), dict(response.headers.items())

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
        self.assertTrue(created["computer_vision"]["started"])

        status, active = self.request("GET", "/sessions/active")
        self.assertEqual(status, 200)
        self.assertEqual(active["active_session"]["session_id"], session_id)

        status, listed = self.request("GET", "/sessions")
        self.assertEqual(status, 200)
        self.assertEqual(listed["sessions"][0]["session_id"], session_id)
        self.assertIn("focus_score", listed["sessions"][0])

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
        self.assertTrue(debug_state["computer_vision"]["running"])

        status, session_detail = self.request("GET", f"/sessions/{session_id}")
        self.assertEqual(status, 200)
        self.assertEqual(session_detail["session"]["session_id"], session_id)

        status, session_intervals = self.request("GET", f"/sessions/{session_id}/intervals")
        self.assertEqual(status, 200)
        self.assertEqual(session_intervals["interval_count"], 1)
        self.assertEqual(session_intervals["intervals"][0]["event_id"], "evt_001")

        status, csv_text, headers = self.request_text("GET", f"/sessions/{session_id}/intervals.csv")
        self.assertEqual(status, 200)
        self.assertIn("text/csv", headers["Content-Type"])
        self.assertIn("event_id,batch_id,session_id", csv_text)
        self.assertIn("evt_001,batch_001", csv_text)

        status, csv_text_query, _ = self.request_text("GET", f"/sessions/{session_id}/intervals?format=csv")
        self.assertEqual(status, 200)
        self.assertEqual(csv_text_query, csv_text)

        status, session_summary = self.request("GET", f"/sessions/{session_id}/summary")
        self.assertEqual(status, 200)
        self.assertEqual(session_summary["summary"]["interval_count"], 1)
        self.assertEqual(session_summary["summary"]["total_duration_ms"], 30000)
        self.assertGreater(session_summary["summary"]["focus_score"], 0)
        self.assertEqual(session_summary["summary"]["camera_session_id"], "2026-03-28T20-14-00Z")
        self.assertEqual(session_summary["summary"]["graph_image_url"], f"/sessions/{session_id}/graph.png")
        self.assertEqual(session_summary["summary"]["distraction_image_count"], 1)
        self.assertEqual(
            session_summary["summary"]["distraction_images"][0]["url"],
            f"/sessions/{session_id}/distraction-images/2026-03-28T20-14-12_distracted.png",
        )

        status, final_dataset = self.request("GET", f"/sessions/{session_id}/final-dataset")
        self.assertEqual(status, 200)
        self.assertEqual(final_dataset["session"]["session_id"], session_id)
        self.assertEqual(len(final_dataset["segments"]), 1)
        self.assertEqual(final_dataset["segments"][0]["merged_productivity_label"], "on_task")
        self.assertEqual(len(final_dataset["summary"]["distraction_images"]), 1)

        status, graph_body, headers = self.request_bytes("GET", f"/sessions/{session_id}/graph.png")
        self.assertEqual(status, 200)
        self.assertIn("image/png", headers["Content-Type"])
        self.assertTrue(graph_body)

        status, distraction_body, headers = self.request_bytes(
            "GET",
            f"/sessions/{session_id}/distraction-images/2026-03-28T20-14-12_distracted.png",
        )
        self.assertEqual(status, 200)
        self.assertIn("image/png", headers["Content-Type"])
        self.assertTrue(distraction_body)

        status, studylcaw_context = self.request("GET", f"/sessions/{session_id}/studyclaw-context")
        self.assertEqual(status, 200)
        self.assertEqual(studylcaw_context["context"]["session_id"], session_id)
        self.assertEqual(studylcaw_context["context"]["agent_ready"], True)

        status, chat_response = self.request(
            "POST",
            "/chat/studyclaw",
            {
                "message": "How did this session go?",
                "session_context": session_id,
                "user_id": "ryan",
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(chat_response["agent_ready"], True)
        self.assertEqual(chat_response["response"]["role"], "assistant")
        self.assertIn("handoff contract is ready", chat_response["response"]["content"])

        status, imported_courses = self.request(
            "POST",
            "/integrations/canvas/courses/import",
            {
                "user_id": "ryan",
                "canvas_instance_domain": "psu.instructure.com",
                "imported_at": "2026-03-28T21:00:00Z",
                "courses": [
                    {
                        "external_course_id": "12345",
                        "name": "CMPSC 132",
                        "course_code": "CMPSC 132",
                        "term_name": "Spring 2026",
                        "workflow_state": "available",
                    }
                ],
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(imported_courses["imported_count"], 1)
        self.assertEqual(imported_courses["courses"][0]["name"], "CMPSC 132")

        status, listed_courses = self.request("GET", "/integrations/canvas/courses?user_id=ryan")
        self.assertEqual(status, 200)
        self.assertEqual(len(listed_courses["courses"]), 1)
        self.assertEqual(listed_courses["courses"][0]["canvas_instance_domain"], "psu.instructure.com")

        status, cleared_courses = self.request(
            "POST",
            "/integrations/canvas/courses/clear",
            {"user_id": "ryan"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(cleared_courses["deleted_count"], 1)

        status, listed_after_clear = self.request("GET", "/integrations/canvas/courses?user_id=ryan")
        self.assertEqual(status, 200)
        self.assertEqual(len(listed_after_clear["courses"]), 0)

        status, stopped = self.request("POST", f"/sessions/{session_id}/stop")
        self.assertEqual(status, 200)
        self.assertEqual(stopped["session"]["status"], "stopped")
        self.assertTrue(stopped["computer_vision"]["stopped"])

    def test_computer_vision_process_exit_stops_active_session(self) -> None:
        autoexit_db_path = self.test_dir / "autoexit.sqlite3"
        autoexit_db_path.unlink(missing_ok=True)
        storage = Storage(str(autoexit_db_path))

        autoexit_script = self.test_dir / "fake_cv_autoexit.py"
        autoexit_script.write_text(
            "import os\nfrom pathlib import Path\nimport time\n"
            "ready_file = os.environ.get('STUDYCLAW_CV_READY_FILE')\n"
            "if ready_file:\n"
            "    Path(ready_file).write_text('ready\\n', encoding='utf-8')\n"
            "time.sleep(2.0)\n",
            encoding="utf-8",
        )

        manager = ComputerVisionManager(
            storage,
            script_path=str(autoexit_script),
            logs_dir=str(self.test_dir / "cv-logs-autoexit"),
        )

        session = storage.create_session(
            session_id="sess_autoexit",
            user_id="ryan",
            course="CMPSC 132",
            assignment=None,
            planned_duration_minutes=30,
            created_at="2026-03-29T05:00:00Z",
        )

        started = manager.start_session(session)
        self.assertTrue(started["started"])

        for _ in range(40):
            if storage.get_active_session() is None:
                break
            time.sleep(0.1)

        self.assertIsNone(storage.get_active_session())


if __name__ == "__main__":
    unittest.main()
