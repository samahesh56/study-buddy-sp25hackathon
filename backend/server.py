import csv
import io
import json
import os
import sys
import uuid
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from mimetypes import guess_type
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from backend.cv_manager import ComputerVisionManager
from backend.final_dataset import FinalDatasetService
from backend.storage import Storage
from backend.studyclaw import build_studyclaw_context, generate_placeholder_chat_response


ROOT = Path(__file__).resolve().parent
DEFAULT_DB_PATH = ROOT / "data" / "studyclaw.sqlite3"
DEFAULT_CAMERA_DATA_DIR = ROOT.parent / "ComputerVision" / "Data"
DEFAULT_CAMERA_SCRIPT_PATH = ROOT.parent / "ComputerVision" / "attention_classifier.py"
DEFAULT_CAMERA_LOGS_DIR = ROOT / "logs" / "computer-vision"
INTERVAL_CSV_COLUMNS = (
    "event_id",
    "batch_id",
    "session_id",
    "user_id",
    "event_type",
    "client_created_at",
    "interval_start",
    "interval_end",
    "duration_ms",
    "tab_id",
    "window_id",
    "tab_url",
    "tab_domain",
    "normalized_domain",
    "tab_title",
    "is_browser_focused",
    "is_tab_active",
    "page_visible",
    "scroll_count",
    "click_count",
    "keystroke_count",
    "transition_in_reason",
    "transition_out_reason",
    "segment_index",
    "is_partial_segment",
    "extension_version",
    "collector_id",
    "server_received_at",
)


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_session_id(now: datetime | None = None) -> str:
    current = now or datetime.now(UTC)
    return f"sess_{current.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    handler.end_headers()
    handler.wfile.write(body)


def csv_response(
    handler: BaseHTTPRequestHandler,
    status: int,
    rows: list[dict[str, Any]],
    fieldnames: tuple[str, ...],
    filename: str,
) -> None:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in fieldnames})

    body = buffer.getvalue().encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/csv; charset=utf-8")
    handler.send_header("Content-Disposition", f'attachment; filename="{filename}"')
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    handler.end_headers()
    handler.wfile.write(body)


def binary_response(handler: BaseHTTPRequestHandler, status: int, body: bytes, content_type: str) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    handler.end_headers()
    handler.wfile.write(body)


def load_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    content_length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(content_length) if content_length else b"{}"
    return json.loads(raw.decode("utf-8") or "{}")


def validate_event(event: dict[str, Any], batch_session_id: str) -> list[str]:
    required = [
        "event_id",
        "event_type",
        "session_id",
        "client_created_at",
        "interval_start",
        "interval_end",
        "duration_ms",
        "is_browser_focused",
        "scroll_count",
        "click_count",
        "keystroke_count",
        "transition_in_reason",
        "transition_out_reason",
        "segment_index",
    ]
    missing = [field for field in required if field not in event]
    errors = [f"missing field: {field}" for field in missing]
    if event.get("event_type") != "browser_interval":
        errors.append("event_type must be browser_interval")
    if event.get("session_id") != batch_session_id:
        errors.append("event session_id must match batch session_id")
    if not isinstance(event.get("duration_ms"), int) or event["duration_ms"] < 0:
        errors.append("duration_ms must be a non-negative integer")
    for count_field in ("scroll_count", "click_count", "keystroke_count", "segment_index"):
        value = event.get(count_field)
        if not isinstance(value, int) or value < 0:
            errors.append(f"{count_field} must be a non-negative integer")
    return errors


class StudyClawHandler(BaseHTTPRequestHandler):
    storage: Storage
    final_dataset: FinalDatasetService
    cv_manager: ComputerVisionManager

    def do_OPTIONS(self) -> None:
        json_response(self, HTTPStatus.NO_CONTENT, {})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path_parts = [part for part in parsed.path.split("/") if part]

        if parsed.path == "/health":
            json_response(self, HTTPStatus.OK, {"status": "ok", "server_time": utc_now_iso()})
            return

        if parsed.path == "/sessions/active":
            json_response(self, HTTPStatus.OK, {"active_session": self.storage.get_active_session()})
            return

        if parsed.path == "/sessions/list":
            json_response(self, HTTPStatus.OK, {"sessions": self.storage.list_sessions()})
            return

        if parsed.path == "/debug/state":
            state = self.storage.debug_state()
            state["computer_vision"] = self.cv_manager.get_status()
            json_response(self, HTTPStatus.OK, state)
            return

        if parsed.path == "/integrations/canvas/courses":
            query = parse_qs(parsed.query)
            user_id = query.get("user_id", [None])[0]
            if not user_id:
                json_response(self, HTTPStatus.BAD_REQUEST, {"error": "user_id query parameter is required"})
                return
            json_response(self, HTTPStatus.OK, {"courses": self.storage.list_canvas_courses(user_id)})
            return

        if parsed.path == "/sessions":
            query = parse_qs(parsed.query)
            session_id = query.get("session_id", [None])[0]
            if not session_id:
                json_response(self, HTTPStatus.OK, {"sessions": self.final_dataset.list_sessions()})
                return
            session = self.final_dataset.get_enriched_session(session_id)
            if not session:
                json_response(self, HTTPStatus.NOT_FOUND, {"error": "session not found"})
                return
            json_response(self, HTTPStatus.OK, {"session": session})
            return

        if len(path_parts) >= 2 and path_parts[0] == "sessions":
            session_id = path_parts[1]
            session = self.final_dataset.get_enriched_session(session_id)
            if not session:
                json_response(self, HTTPStatus.NOT_FOUND, {"error": "session not found"})
                return

            if len(path_parts) == 2:
                json_response(self, HTTPStatus.OK, {"session": session})
                return

            if len(path_parts) == 3 and path_parts[2] in {"intervals", "intervals.csv"}:
                query = parse_qs(parsed.query)
                limit_raw = query.get("limit", [None])[0]
                limit = int(limit_raw) if limit_raw and limit_raw.isdigit() else None
                intervals = self.storage.list_session_intervals(session_id, limit=limit)
                wants_csv = path_parts[2] == "intervals.csv" or query.get("format", [None])[0] == "csv"
                if wants_csv:
                    csv_response(
                        self,
                        HTTPStatus.OK,
                        intervals,
                        INTERVAL_CSV_COLUMNS,
                        f"{session_id}-browser-intervals.csv",
                    )
                    return
                json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "session": session,
                        "interval_count": len(intervals),
                        "intervals": intervals,
                    },
                )
                return

            if len(path_parts) == 3 and path_parts[2] == "summary":
                summary = self.final_dataset.get_session_summary(session_id)
                json_response(self, HTTPStatus.OK, {"summary": summary})
                return

            if len(path_parts) == 3 and path_parts[2] == "final-dataset":
                dataset = self.final_dataset.get_final_dataset(session_id)
                json_response(self, HTTPStatus.OK, dataset or {})
                return

            if len(path_parts) == 3 and path_parts[2] == "graph.png":
                graph_path = self.final_dataset.get_session_graph_path(session_id)
                if not graph_path:
                    json_response(self, HTTPStatus.NOT_FOUND, {"error": "graph not found"})
                    return
                binary_response(
                    self,
                    HTTPStatus.OK,
                    graph_path.read_bytes(),
                    guess_type(graph_path.name)[0] or "image/png",
                )
                return

            if len(path_parts) == 4 and path_parts[2] == "distraction-images":
                image_name = path_parts[3]
                image_paths = self.final_dataset.get_session_distraction_image_paths(session_id)
                image_path = image_paths.get(image_name)
                if not image_path:
                    json_response(self, HTTPStatus.NOT_FOUND, {"error": "distraction image not found"})
                    return
                binary_response(
                    self,
                    HTTPStatus.OK,
                    image_path.read_bytes(),
                    guess_type(image_path.name)[0] or "image/png",
                )
                return

            if len(path_parts) == 3 and path_parts[2] == "studyclaw-context":
                context = build_studyclaw_context(self.storage, session_id)
                json_response(self, HTTPStatus.OK, {"context": context})
                return

        json_response(self, HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/sessions":
            body = load_json_body(self)
            session = self.storage.create_session(
                session_id=new_session_id(),
                user_id=body.get("user_id"),
                course=body.get("course"),
                assignment=body.get("assignment"),
                planned_duration_minutes=body.get("planned_duration_minutes"),
                created_at=utc_now_iso(),
            )
            cv_status = self.cv_manager.start_session(session)
            if not cv_status.get("started"):
                self.storage.stop_session(session["session_id"], utc_now_iso())
                json_response(
                    self,
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {
                        "error": "computer vision failed to start",
                        "session": self.final_dataset.get_enriched_session(session["session_id"]),
                        "computer_vision": cv_status,
                    },
                )
                return
            json_response(self, HTTPStatus.CREATED, {"session": session, "computer_vision": cv_status})
            return

        if parsed.path.startswith("/sessions/") and parsed.path.endswith("/stop"):
            session_id = parsed.path.split("/")[2]
            cv_status = self.cv_manager.stop_session(session_id)
            stopped = self.storage.stop_session(session_id, utc_now_iso())
            if not stopped:
                json_response(self, HTTPStatus.NOT_FOUND, {"error": "active session not found"})
                return
            json_response(self, HTTPStatus.OK, {"session": stopped, "computer_vision": cv_status})
            return

        if parsed.path == "/telemetry/browser-batch":
            body = load_json_body(self)
            batch_errors = []
            for field in ("batch_id", "session_id", "source", "sent_at", "events"):
                if field not in body:
                    batch_errors.append(f"missing field: {field}")
            if batch_errors:
                json_response(self, HTTPStatus.BAD_REQUEST, {"error": "invalid batch", "details": batch_errors})
                return

            existing_session = self.storage.get_session(body["session_id"])
            if not existing_session:
                json_response(self, HTTPStatus.BAD_REQUEST, {"error": "unknown session_id"})
                return

            if not isinstance(body["events"], list) or not body["events"]:
                json_response(self, HTTPStatus.BAD_REQUEST, {"error": "events must be a non-empty list"})
                return

            event_errors: list[dict[str, Any]] = []
            for event in body["events"]:
                errors = validate_event(event, body["session_id"])
                if errors:
                    event_errors.append({"event_id": event.get("event_id"), "errors": errors})
            if event_errors:
                json_response(self, HTTPStatus.BAD_REQUEST, {"error": "invalid events", "details": event_errors})
                return

            received_at = utc_now_iso()
            accepted_event_ids, duplicate_event_ids = self.storage.insert_batch(body, body["events"], received_at)
            json_response(
                self,
                HTTPStatus.OK,
                {
                    "batch_id": body["batch_id"],
                    "accepted": True,
                    "accepted_event_ids": accepted_event_ids,
                    "duplicate_event_ids": duplicate_event_ids,
                    "server_received_at": received_at,
                },
            )
            return

        if parsed.path == "/integrations/canvas/courses/import":
            body = load_json_body(self)
            for field in ("user_id", "canvas_instance_domain", "imported_at", "courses"):
                if field not in body:
                    json_response(self, HTTPStatus.BAD_REQUEST, {"error": f"missing field: {field}"})
                    return

            if not isinstance(body["courses"], list) or not body["courses"]:
                json_response(self, HTTPStatus.BAD_REQUEST, {"error": "courses must be a non-empty list"})
                return

            for course in body["courses"]:
                for field in ("external_course_id", "name"):
                    if field not in course:
                        json_response(self, HTTPStatus.BAD_REQUEST, {"error": f"course missing field: {field}"})
                        return

            imported_count = self.storage.upsert_canvas_courses(
                user_id=body["user_id"],
                canvas_instance_domain=body["canvas_instance_domain"],
                imported_at=body["imported_at"],
                courses=body["courses"],
            )
            json_response(
                self,
                HTTPStatus.OK,
                {
                    "imported": True,
                    "imported_count": imported_count,
                    "courses": self.storage.list_canvas_courses(body["user_id"]),
                },
            )
            return

        if parsed.path == "/integrations/canvas/courses/clear":
            body = load_json_body(self)
            user_id = body.get("user_id")
            if not user_id:
                json_response(self, HTTPStatus.BAD_REQUEST, {"error": "missing field: user_id"})
                return
            deleted = self.storage.clear_canvas_courses(user_id)
            json_response(self, HTTPStatus.OK, {"cleared": True, "deleted_count": deleted})
            return

        if parsed.path == "/chat/studyclaw":
            body = load_json_body(self)
            message = (body.get("message") or "").strip()
            if not message:
                json_response(self, HTTPStatus.BAD_REQUEST, {"error": "missing field: message"})
                return

            session_context = body.get("session_context")
            user_id = body.get("user_id")
            session_id = None

            if session_context and session_context != "none":
                if session_context == "latest":
                    sessions = self.storage.list_sessions()
                    for session in sessions:
                        if not user_id or session.get("user_id") == user_id:
                            session_id = session.get("session_id")
                            break
                else:
                    session_id = session_context

            context = build_studyclaw_context(self.storage, session_id) if session_id else None
            response = generate_placeholder_chat_response(context, message)
            response["timestamp"] = utc_now_iso()
            json_response(
                self,
                HTTPStatus.OK,
                {
                    "response": response,
                    "agent_ready": True,
                    "agent_mode": "placeholder",
                    "context": context,
                },
            )
            return

        json_response(self, HTTPStatus.NOT_FOUND, {"error": "not found"})

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stdout.write(f"{self.address_string()} - {fmt % args}\n")


def create_server(
    host: str,
    port: int,
    db_path: str | None = None,
    camera_data_dir: str | None = None,
    camera_script_path: str | None = None,
) -> ThreadingHTTPServer:
    storage = Storage(db_path or str(DEFAULT_DB_PATH))
    handler_cls = StudyClawHandler
    handler_cls.storage = storage
    handler_cls.final_dataset = FinalDatasetService(
        storage,
        camera_data_dir=camera_data_dir or str(DEFAULT_CAMERA_DATA_DIR),
    )
    handler_cls.cv_manager = ComputerVisionManager(
        storage,
        script_path=camera_script_path or str(DEFAULT_CAMERA_SCRIPT_PATH),
        logs_dir=str(DEFAULT_CAMERA_LOGS_DIR),
    )
    return ThreadingHTTPServer((host, port), handler_cls)


def main() -> None:
    host = os.environ.get("STUDYCLAW_HOST", "127.0.0.1")
    port = int(os.environ.get("STUDYCLAW_PORT", "8000"))
    db_path = os.environ.get("STUDYCLAW_DB_PATH", str(DEFAULT_DB_PATH))
    camera_data_dir = os.environ.get("STUDYCLAW_CAMERA_DATA_DIR", str(DEFAULT_CAMERA_DATA_DIR))
    camera_script_path = os.environ.get("STUDYCLAW_CAMERA_SCRIPT_PATH", str(DEFAULT_CAMERA_SCRIPT_PATH))
    server = create_server(host, port, db_path, camera_data_dir, camera_script_path)
    print(f"StudyClaw backend listening on http://{host}:{port} using {db_path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
