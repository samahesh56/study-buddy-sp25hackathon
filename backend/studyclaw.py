from __future__ import annotations

from typing import Any

from backend.storage import Storage


def build_recent_history_digest(
    storage: Storage,
    user_id: str | None,
    exclude_session_id: str | None = None,
    limit: int = 8,
) -> dict[str, Any]:
    sessions = [session for session in storage.list_sessions() if session.get("status") == "stopped"]
    if user_id:
        sessions = [session for session in sessions if session.get("user_id") == user_id]
    if exclude_session_id:
        sessions = [session for session in sessions if session.get("session_id") != exclude_session_id]

    recent_sessions = sessions[:limit]
    summaries = [storage.get_session_summary(session["session_id"]) for session in recent_sessions]
    summaries = [summary for summary in summaries if summary]

    if not summaries:
        return {
            "sessions_considered": 0,
            "average_focus_score": None,
            "average_on_task_ratio": None,
            "common_distractions": [],
            "typical_session_length_minutes": None,
            "recurring_patterns": [],
        }

    total_minutes = [round((summary.get("total_duration_ms") or 0) / 60000) for summary in summaries]
    top_domains: dict[str, int] = {}
    for summary in summaries:
        for domain in summary.get("top_domains", []):
            name = domain.get("domain")
            if not name:
                continue
            top_domains[name] = top_domains.get(name, 0) + 1

    sorted_domains = sorted(top_domains.items(), key=lambda item: (-item[1], item[0]))
    return {
        "sessions_considered": len(summaries),
        "average_focus_score": None,
        "average_on_task_ratio": None,
        "common_distractions": [name for name, _count in sorted_domains[:3]],
        "typical_session_length_minutes": round(sum(total_minutes) / len(total_minutes), 1) if total_minutes else None,
        "recurring_patterns": [
            "Raw telemetry is available, but processed focus analytics are still pending backend integration.",
            "This digest is ready to be replaced with true recurring-pattern logic once the analytics pipeline lands.",
        ],
    }


def build_studyclaw_context(storage: Storage, session_id: str) -> dict[str, Any] | None:
    session = storage.get_session(session_id)
    if not session:
        return None

    current_summary = storage.get_session_summary(session_id)
    history_digest = build_recent_history_digest(
        storage,
        user_id=session.get("user_id"),
        exclude_session_id=session_id,
    )

    return {
        "session_id": session_id,
        "user_id": session.get("user_id"),
        "current_session": current_summary,
        "recent_history_digest": history_digest,
        "memory_excerpts": [],
        "agent_ready": True,
        "agent_mode": "placeholder",
    }


def generate_placeholder_chat_response(context: dict[str, Any] | None, message: str) -> dict[str, Any]:
    current_session = context.get("current_session") if context else None
    recent_history = context.get("recent_history_digest") if context else None
    session_meta = current_session.get("session") if current_session else {}
    course = session_meta.get("course") or "this session"
    interval_count = current_session.get("interval_count") if current_session else 0
    total_minutes = round((current_session.get("total_duration_ms") or 0) / 60000) if current_session else 0
    sessions_considered = recent_history.get("sessions_considered") if recent_history else 0

    content = (
        "OpenClaw is not connected yet, but the handoff contract is ready. "
        f"I received your message about \"{message}\" with context for {course}. "
        f"The current session includes {interval_count} raw intervals across about {total_minutes} minutes, "
        f"and the backend also prepared a recent-history digest spanning {sessions_considered} prior sessions. "
        "Once the agent is wired in, this same endpoint can forward the structured session summary and history digest "
        "directly into the OpenClaw coaching layer."
    )

    return {
        "role": "assistant",
        "content": content,
        "context": {
            "session_id": context.get("session_id") if context else None,
            "agent_mode": context.get("agent_mode") if context else "placeholder",
            "history_sessions_considered": sessions_considered,
        },
    }
