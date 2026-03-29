import os
import sys
import textwrap
import unittest
from pathlib import Path

from backend.studyclaw import generate_studyclaw_chat_response


class StudyClawOpenClawAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.test_dir = Path(__file__).resolve().parent / ".tmp" / "studyclaw"
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.previous_env = {
            "STUDYCLAW_CHAT_MODE": os.environ.get("STUDYCLAW_CHAT_MODE"),
            "STUDYCLAW_OPENCLAW_COMMAND": os.environ.get("STUDYCLAW_OPENCLAW_COMMAND"),
            "STUDYCLAW_OPENCLAW_AGENT": os.environ.get("STUDYCLAW_OPENCLAW_AGENT"),
            "STUDYCLAW_OPENCLAW_THINKING": os.environ.get("STUDYCLAW_OPENCLAW_THINKING"),
            "STUDYCLAW_OPENCLAW_TIMEOUT_SECONDS": os.environ.get("STUDYCLAW_OPENCLAW_TIMEOUT_SECONDS"),
        }

    def tearDown(self) -> None:
        for key, value in self.previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_openclaw_command_string_with_args_returns_assistant_text(self) -> None:
        script_path = self._write_fake_openclaw_script(
            """
            import json
            import sys

            message = sys.argv[sys.argv.index("--message") + 1]
            print("OpenClaw boot log")
            print(json.dumps({
                "payloads": [
                    {"text": "Coach response"},
                    {
                        "text": "Prompt echoed: "
                        + (
                            "metrics="
                            + ("yes" if "CURRENT SESSION METRICS:" in message else "no")
                            + ",dataset="
                            + ("yes" if "CURRENT SESSION DATASET:" in message else "no")
                        )
                    },
                ],
                "meta": {
                    "agentMeta": {
                        "provider": "local-test",
                        "model": "fake-openclaw",
                        "sessionId": "agent-test-123",
                    }
                }
            }))
            print("OpenClaw shutdown log")
            """
        )
        os.environ["STUDYCLAW_CHAT_MODE"] = "openclaw"
        os.environ["STUDYCLAW_OPENCLAW_COMMAND"] = f'"{sys.executable}" "{script_path}"'
        os.environ["STUDYCLAW_OPENCLAW_AGENT"] = "session-coach"
        os.environ["STUDYCLAW_OPENCLAW_THINKING"] = "low"
        os.environ["STUDYCLAW_OPENCLAW_TIMEOUT_SECONDS"] = "5"

        context = {
            "session_id": "sess_123",
            "session": {"course": "CMPSC 132", "assignment": "Homework 3"},
            "current_session": {
                "focus_score": 87.5,
                "on_task_ratio": 0.81,
                "away_ratio": 0.06,
                "distraction_event_count": 2,
                "top_domains": [{"domain": "docs.google.com"}],
                "top_distraction_domains": [{"domain": "reddit.com"}],
                "top_relevant_domains": [{"domain": "docs.google.com"}],
                "timeline_highlights": [],
                "system_observations": ["Test observation"],
            },
            "current_dataset": {
                "session": {"session_id": "sess_123", "status": "stopped"},
                "camera_artifact": {
                    "camera_session_id": "camera_123",
                    "started_at": "2026-03-29T11:00:00Z",
                    "ended_at": "2026-03-29T11:30:00Z",
                    "graph_path": "C:/tmp/graph.png",
                    "distraction_images": [
                        {
                            "filename": "snap1.png",
                            "captured_at": "2026-03-29T11:05:00Z",
                            "url": "/sessions/sess_123/distraction-images/snap1.png",
                        }
                    ],
                },
                "segments": [
                    {
                        "segment_start": "2026-03-29T11:00:00Z",
                        "segment_end": "2026-03-29T11:00:30Z",
                        "duration_ms": 30000,
                        "browser_domain": "docs.google.com",
                        "browser_title": "Notes",
                        "camera_attention_state": "FOCUSED",
                        "camera_focus_score": 91.2,
                        "camera_phone_flag": False,
                        "merged_attention_label": "focused",
                        "merged_productivity_label": "on_task",
                    }
                ],
            },
            "recent_history_digest": {
                "sessions_considered": 3,
                "average_focus_score": 79.1,
                "average_on_task_ratio": 0.71,
                "common_distractions": ["reddit.com"],
                "typical_session_length_minutes": 48.0,
                "recurring_patterns": ["Recent sessions averaged a focus score of 79.1."],
            },
        }

        response = generate_studyclaw_chat_response(context, "How did I do?")

        self.assertEqual(response["role"], "assistant")
        self.assertEqual(response["context"]["agent_mode"], "openclaw")
        self.assertEqual(response["context"]["provider"], "local-test")
        self.assertEqual(response["context"]["model"], "fake-openclaw")
        self.assertEqual(response["context"]["agent_session_id"], "agent-test-123")
        self.assertIn("Coach response", response["content"])
        self.assertIn("Prompt echoed: metrics=yes,dataset=yes", response["content"])

    def test_openclaw_failure_falls_back_to_placeholder_response(self) -> None:
        script_path = self._write_fake_openclaw_script(
            """
            import sys

            print("adapter failed", file=sys.stderr)
            raise SystemExit(2)
            """
        )
        os.environ["STUDYCLAW_CHAT_MODE"] = "openclaw"
        os.environ["STUDYCLAW_OPENCLAW_COMMAND"] = f'"{sys.executable}" "{script_path}"'
        os.environ["STUDYCLAW_OPENCLAW_TIMEOUT_SECONDS"] = "5"

        context = {
            "session_id": "sess_456",
            "session": {"course": "Math 140"},
            "current_session": {"interval_count": 4, "actual_duration_minutes": 32},
            "recent_history_digest": {"sessions_considered": 5},
        }

        response = generate_studyclaw_chat_response(context, "What happened?")

        self.assertEqual(response["context"]["agent_mode"], "placeholder-fallback")
        self.assertIn("OpenClaw is not connected yet", response["content"])
        self.assertIn("adapter failed", response["context"]["fallback_error"])

    def _write_fake_openclaw_script(self, body: str) -> Path:
        script_path = self.test_dir / f"fake_openclaw_{self.id().rsplit('.', 1)[-1]}.py"
        script_path.write_text(textwrap.dedent(body).strip() + "\n", encoding="utf-8")
        return script_path


if __name__ == "__main__":
    unittest.main()
