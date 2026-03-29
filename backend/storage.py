import json
import sqlite3
import threading
from pathlib import Path
from typing import Any


class Storage:
    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    course TEXT,
                    assignment TEXT,
                    planned_duration_minutes INTEGER,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    stopped_at TEXT
                );

                CREATE TABLE IF NOT EXISTS telemetry_batches (
                    batch_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    user_id TEXT,
                    source TEXT NOT NULL,
                    extension_version TEXT,
                    sent_at TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    sequence_number INTEGER,
                    raw_payload_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS browser_intervals_raw (
                    event_id TEXT PRIMARY KEY,
                    batch_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    user_id TEXT,
                    event_type TEXT NOT NULL,
                    client_created_at TEXT NOT NULL,
                    interval_start TEXT NOT NULL,
                    interval_end TEXT NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    tab_id INTEGER,
                    window_id INTEGER,
                    tab_url TEXT,
                    tab_domain TEXT,
                    normalized_domain TEXT,
                    tab_title TEXT,
                    is_browser_focused INTEGER NOT NULL,
                    is_tab_active INTEGER NOT NULL,
                    page_visible INTEGER,
                    scroll_count INTEGER NOT NULL,
                    click_count INTEGER NOT NULL,
                    keystroke_count INTEGER NOT NULL,
                    transition_in_reason TEXT NOT NULL,
                    transition_out_reason TEXT NOT NULL,
                    segment_index INTEGER NOT NULL,
                    is_partial_segment INTEGER NOT NULL,
                    extension_version TEXT,
                    collector_id TEXT,
                    server_received_at TEXT NOT NULL,
                    raw_event_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS canvas_courses (
                    user_id TEXT NOT NULL,
                    canvas_instance_domain TEXT NOT NULL,
                    external_course_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    course_code TEXT,
                    term_name TEXT,
                    workflow_state TEXT,
                    imported_at TEXT NOT NULL,
                    raw_course_json TEXT NOT NULL,
                    PRIMARY KEY (user_id, canvas_instance_domain, external_course_id)
                );

                CREATE INDEX IF NOT EXISTS idx_sessions_status_started_at
                ON sessions (status, started_at DESC);

                CREATE INDEX IF NOT EXISTS idx_batches_session_received_at
                ON telemetry_batches (session_id, received_at DESC);

                CREATE INDEX IF NOT EXISTS idx_intervals_session_start
                ON browser_intervals_raw (session_id, interval_start ASC);

                CREATE INDEX IF NOT EXISTS idx_intervals_received_at
                ON browser_intervals_raw (server_received_at DESC);

                CREATE INDEX IF NOT EXISTS idx_canvas_courses_user_imported
                ON canvas_courses (user_id, imported_at DESC);
                """
            )
            existing_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
            }
            if "course" not in existing_columns:
                conn.execute("ALTER TABLE sessions ADD COLUMN course TEXT")
            if "assignment" not in existing_columns:
                conn.execute("ALTER TABLE sessions ADD COLUMN assignment TEXT")
            if "planned_duration_minutes" not in existing_columns:
                conn.execute("ALTER TABLE sessions ADD COLUMN planned_duration_minutes INTEGER")
            conn.commit()

    def create_session(
        self,
        session_id: str,
        user_id: str | None,
        course: str | None,
        assignment: str | None,
        planned_duration_minutes: int | None,
        created_at: str,
    ) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE sessions SET status = 'stopped', stopped_at = ? WHERE status = 'active'", (created_at,))
            conn.execute(
                """
                INSERT INTO sessions (
                    session_id, user_id, course, assignment, planned_duration_minutes,
                    status, created_at, started_at, stopped_at
                )
                VALUES (?, ?, ?, ?, ?, 'active', ?, ?, NULL)
                """,
                (session_id, user_id, course, assignment, planned_duration_minutes, created_at, created_at),
            )
            conn.commit()
        return self.get_session(session_id)

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        return dict(row) if row else None

    def get_active_session(self) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE status = 'active' ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT s.*,
                       COALESCE(ROUND(SUM(b.duration_ms) / 60000.0), 0) AS actual_duration_minutes
                FROM sessions s
                LEFT JOIN browser_intervals_raw b ON b.session_id = s.session_id
                GROUP BY s.session_id
                ORDER BY s.started_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def stop_session(self, session_id: str, stopped_at: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET status = 'stopped', stopped_at = ? WHERE session_id = ? AND status = 'active'",
                (stopped_at, session_id),
            )
            conn.commit()
        return self.get_session(session_id)

    def insert_batch(
        self,
        batch: dict[str, Any],
        events: list[dict[str, Any]],
        received_at: str,
    ) -> tuple[list[str], list[str]]:
        accepted_event_ids: list[str] = []
        duplicate_event_ids: list[str] = []

        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO telemetry_batches (
                    batch_id, session_id, user_id, source, extension_version,
                    sent_at, received_at, sequence_number, raw_payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch["batch_id"],
                    batch["session_id"],
                    batch.get("user_id"),
                    batch["source"],
                    batch.get("extension_version"),
                    batch["sent_at"],
                    received_at,
                    batch.get("sequence_number"),
                    json.dumps(batch),
                ),
            )

            for event in events:
                normalized_domain = normalize_domain(event.get("tab_domain") or event.get("tab_url"))
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO browser_intervals_raw (
                        event_id, batch_id, session_id, user_id, event_type, client_created_at,
                        interval_start, interval_end, duration_ms, tab_id, window_id,
                        tab_url, tab_domain, normalized_domain, tab_title,
                        is_browser_focused, is_tab_active, page_visible,
                        scroll_count, click_count, keystroke_count,
                        transition_in_reason, transition_out_reason,
                        segment_index, is_partial_segment, extension_version,
                        collector_id, server_received_at, raw_event_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event["event_id"],
                        batch["batch_id"],
                        event["session_id"],
                        event.get("user_id") or batch.get("user_id"),
                        event["event_type"],
                        event["client_created_at"],
                        event["interval_start"],
                        event["interval_end"],
                        event["duration_ms"],
                        event.get("tab_id"),
                        event.get("window_id"),
                        event.get("tab_url"),
                        event.get("tab_domain"),
                        normalized_domain,
                        event.get("tab_title"),
                        int(bool(event["is_browser_focused"])),
                        int(bool(event.get("is_tab_active", True))),
                        None if event.get("page_visible") is None else int(bool(event["page_visible"])),
                        event["scroll_count"],
                        event["click_count"],
                        event["keystroke_count"],
                        event["transition_in_reason"],
                        event["transition_out_reason"],
                        event["segment_index"],
                        int(bool(event.get("is_partial_segment", False))),
                        event.get("extension_version") or batch.get("extension_version"),
                        event.get("collector_id"),
                        received_at,
                        json.dumps(event),
                    ),
                )
                if cursor.rowcount == 1:
                    accepted_event_ids.append(event["event_id"])
                else:
                    duplicate_event_ids.append(event["event_id"])

            conn.commit()

        return accepted_event_ids, duplicate_event_ids

    def debug_state(self) -> dict[str, Any]:
        with self._connect() as conn:
            active_session = self.get_active_session()
            batch_count = conn.execute("SELECT COUNT(*) FROM telemetry_batches").fetchone()[0]
            interval_count = conn.execute("SELECT COUNT(*) FROM browser_intervals_raw").fetchone()[0]
            recent_intervals = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT event_id, session_id, interval_start, interval_end, duration_ms,
                           tab_domain, tab_title, scroll_count, click_count, keystroke_count,
                           transition_in_reason, transition_out_reason, server_received_at
                    FROM browser_intervals_raw
                    ORDER BY server_received_at DESC
                    LIMIT 20
                    """
                ).fetchall()
            ]

        return {
            "active_session": active_session,
            "batch_count": batch_count,
            "interval_count": interval_count,
            "recent_intervals": recent_intervals,
        }

    def list_session_intervals(self, session_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT event_id, batch_id, session_id, user_id, event_type, client_created_at,
                   interval_start, interval_end, duration_ms, tab_id, window_id,
                   tab_url, tab_domain, normalized_domain, tab_title,
                   is_browser_focused, is_tab_active, page_visible,
                   scroll_count, click_count, keystroke_count,
                   transition_in_reason, transition_out_reason,
                   segment_index, is_partial_segment, extension_version,
                   collector_id, server_received_at
            FROM browser_intervals_raw
            WHERE session_id = ?
            ORDER BY interval_start ASC
        """
        params: tuple[Any, ...] = (session_id,)
        if limit is not None:
            query += " LIMIT ?"
            params = (session_id, limit)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_session_summary(self, session_id: str) -> dict[str, Any] | None:
        session = self.get_session(session_id)
        if not session:
            return None

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS interval_count,
                    COALESCE(SUM(duration_ms), 0) AS total_duration_ms,
                    COALESCE(SUM(scroll_count), 0) AS total_scroll_count,
                    COALESCE(SUM(click_count), 0) AS total_click_count,
                    COALESCE(SUM(keystroke_count), 0) AS total_keystroke_count,
                    SUM(CASE WHEN transition_out_reason = 'segment_rollover' THEN 1 ELSE 0 END) AS rollover_count,
                    MIN(interval_start) AS first_interval_start,
                    MAX(interval_end) AS last_interval_end
                FROM browser_intervals_raw
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()

            top_domains = [
                dict(domain=row["tab_domain"], interval_count=row["interval_count"], total_duration_ms=row["total_duration_ms"])
                for row in conn.execute(
                    """
                    SELECT tab_domain, COUNT(*) AS interval_count, COALESCE(SUM(duration_ms), 0) AS total_duration_ms
                    FROM browser_intervals_raw
                    WHERE session_id = ?
                    GROUP BY tab_domain
                    ORDER BY total_duration_ms DESC, interval_count DESC
                    LIMIT 10
                    """,
                    (session_id,),
                ).fetchall()
            ]

        summary = dict(row) if row else {}
        summary["session"] = session
        summary["top_domains"] = top_domains
        return summary

    def upsert_canvas_courses(
        self,
        user_id: str,
        canvas_instance_domain: str,
        imported_at: str,
        courses: list[dict[str, Any]],
    ) -> int:
        with self._lock, self._connect() as conn:
            for course in courses:
                conn.execute(
                    """
                    INSERT INTO canvas_courses (
                        user_id, canvas_instance_domain, external_course_id,
                        name, course_code, term_name, workflow_state,
                        imported_at, raw_course_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, canvas_instance_domain, external_course_id)
                    DO UPDATE SET
                        name = excluded.name,
                        course_code = excluded.course_code,
                        term_name = excluded.term_name,
                        workflow_state = excluded.workflow_state,
                        imported_at = excluded.imported_at,
                        raw_course_json = excluded.raw_course_json
                    """,
                    (
                        user_id,
                        canvas_instance_domain,
                        str(course["external_course_id"]),
                        course["name"],
                        course.get("course_code"),
                        course.get("term_name"),
                        course.get("workflow_state"),
                        imported_at,
                        json.dumps(course),
                    ),
                )
            conn.commit()
        return len(courses)

    def list_canvas_courses(self, user_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT user_id, canvas_instance_domain, external_course_id, name,
                       course_code, term_name, workflow_state, imported_at
                FROM canvas_courses
                WHERE user_id = ?
                ORDER BY imported_at DESC, name ASC
                """,
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]


def normalize_domain(raw_value: str | None) -> str | None:
    if not raw_value:
        return None
    value = raw_value.strip().lower()
    if "://" in value:
        value = value.split("://", 1)[1]
    value = value.split("/", 1)[0]
    if value.startswith("www."):
        value = value[4:]
    return value or None
