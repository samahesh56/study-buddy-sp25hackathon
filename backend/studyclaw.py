from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from typing import Any

if os.name == "nt":
    from ctypes import POINTER, byref, c_int, windll
    from ctypes.wintypes import LPCWSTR, LPWSTR

from backend.final_dataset import FinalDatasetService
from backend.storage import Storage


def build_recent_history_digest(
    storage: Storage,
    final_dataset: FinalDatasetService,
    user_id: str | None,
    exclude_session_id: str | None = None,
    limit: int = 8,
) -> dict[str, Any]:
    sessions = [session for session in final_dataset.list_sessions() if session.get("status") == "stopped"]
    if user_id:
        sessions = [session for session in sessions if session.get("user_id") == user_id]
    if exclude_session_id:
        sessions = [session for session in sessions if session.get("session_id") != exclude_session_id]

    recent_sessions = sessions[:limit]
    summaries = [final_dataset.get_session_summary(session["session_id"]) for session in recent_sessions]
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

    total_minutes = [summary.get("actual_duration_minutes") or 0 for summary in summaries]
    focus_scores = [summary.get("focus_score") for summary in summaries if summary.get("focus_score") is not None]
    on_task_ratios = [summary.get("on_task_ratio") for summary in summaries if summary.get("on_task_ratio") is not None]
    distraction_domains: dict[str, int] = {}
    for summary in summaries:
        for domain in summary.get("top_distraction_domains", []):
            name = domain.get("domain")
            if not name:
                continue
            distraction_domains[name] = distraction_domains.get(name, 0) + 1

    sorted_domains = sorted(distraction_domains.items(), key=lambda item: (-item[1], item[0]))
    return {
        "sessions_considered": len(summaries),
        "average_focus_score": round(sum(focus_scores) / len(focus_scores), 1) if focus_scores else None,
        "average_on_task_ratio": round(sum(on_task_ratios) / len(on_task_ratios), 3) if on_task_ratios else None,
        "common_distractions": [name for name, _count in sorted_domains[:3]],
        "typical_session_length_minutes": round(sum(total_minutes) / len(total_minutes), 1) if total_minutes else None,
        "recurring_patterns": _build_recurring_patterns(summaries),
    }


def build_studyclaw_context(
    storage: Storage,
    final_dataset: FinalDatasetService,
    session_id: str | None,
) -> dict[str, Any] | None:
    if not session_id:
        return None

    session = storage.get_session(session_id)
    if not session:
        return None

    current_summary = final_dataset.get_session_summary(session_id)
    current_dataset = final_dataset.get_final_dataset(session_id)
    history_digest = build_recent_history_digest(
        storage,
        final_dataset,
        user_id=session.get("user_id"),
        exclude_session_id=session_id,
    )

    return {
        "session_id": session_id,
        "user_id": session.get("user_id"),
        "session": session,
        "current_session": current_summary,
        "current_dataset": current_dataset,
        "recent_history_digest": history_digest,
        "memory_excerpts": [],
        "agent_ready": True,
        "agent_mode": "openclaw",
    }


def generate_studyclaw_chat_response(context: dict[str, Any] | None, message: str) -> dict[str, Any]:
    mode = os.environ.get("STUDYCLAW_CHAT_MODE", "openclaw").strip().lower()
    if mode == "placeholder":
        return _generate_placeholder_chat_response(context, message)

    try:
        return _generate_openclaw_chat_response(context, message)
    except Exception as error:
        fallback = _generate_placeholder_chat_response(context, message)
        fallback.setdefault("context", {})
        fallback["context"]["fallback_error"] = str(error)
        fallback["context"]["agent_mode"] = "placeholder-fallback"
        return fallback


def _generate_openclaw_chat_response(context: dict[str, Any] | None, message: str) -> dict[str, Any]:
    command = os.environ.get("STUDYCLAW_OPENCLAW_COMMAND", "openclaw")
    command_parts = _split_command(command)
    resolved_command = shutil.which(command_parts[0]) if command_parts else None
    executable = resolved_command or (command_parts[0] if command_parts else command)
    if not command_parts or (not resolved_command and not os.path.exists(executable)):
        raise RuntimeError(f"OpenClaw command not found on PATH: {command}")

    agent_id = os.environ.get("STUDYCLAW_OPENCLAW_AGENT", "main")
    thinking = os.environ.get("STUDYCLAW_OPENCLAW_THINKING", "low")
    timeout_seconds = int(os.environ.get("STUDYCLAW_OPENCLAW_TIMEOUT_SECONDS", "180"))
    prompt = _build_openclaw_prompt(context, message)

    result = subprocess.run(
        [
            executable,
            *command_parts[1:],
            "agent",
            "--local",
            "--agent",
            agent_id,
            "--thinking",
            thinking,
            "--json",
            "--message",
            prompt,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout_seconds,
        check=False,
    )

    combined_output = "\n".join(part for part in [result.stdout, result.stderr] if part).strip()
    if result.returncode != 0:
        raise RuntimeError(combined_output or f"OpenClaw exited with code {result.returncode}")

    payload = _extract_json_payload(combined_output)
    text = _extract_openclaw_text(payload)
    agent_meta = payload.get("meta", {}).get("agentMeta", {})

    return {
        "role": "assistant",
        "content": text,
        "context": {
            "session_id": context.get("session_id") if context else None,
            "agent_mode": "openclaw",
            "provider": agent_meta.get("provider"),
            "model": agent_meta.get("model"),
            "agent_session_id": agent_meta.get("sessionId"),
        },
    }


def _build_openclaw_prompt(context: dict[str, Any] | None, message: str) -> str:
    session_summary = context.get("current_session") if context else None
    history_digest = context.get("recent_history_digest") if context else None
    session_meta = context.get("session") if context else None

    summary_payload = {
        "course": session_meta.get("course") if session_meta else None,
        "assignment": session_meta.get("assignment") if session_meta else None,
        "focus_score": session_summary.get("focus_score") if session_summary else None,
        "on_task_ratio": session_summary.get("on_task_ratio") if session_summary else None,
        "away_ratio": session_summary.get("away_ratio") if session_summary else None,
        "distraction_event_count": session_summary.get("distraction_event_count") if session_summary else None,
        "top_domains": session_summary.get("top_domains") if session_summary else [],
        "top_distraction_domains": session_summary.get("top_distraction_domains") if session_summary else [],
        "top_relevant_domains": session_summary.get("top_relevant_domains") if session_summary else [],
        "timeline_highlights": session_summary.get("timeline_highlights") if session_summary else [],
        "system_observations": session_summary.get("system_observations") if session_summary else [],
    }

    history_payload = {
        "sessions_considered": history_digest.get("sessions_considered") if history_digest else 0,
        "average_focus_score": history_digest.get("average_focus_score") if history_digest else None,
        "average_on_task_ratio": history_digest.get("average_on_task_ratio") if history_digest else None,
        "common_distractions": history_digest.get("common_distractions") if history_digest else [],
        "typical_session_length_minutes": history_digest.get("typical_session_length_minutes") if history_digest else None,
        "recurring_patterns": history_digest.get("recurring_patterns") if history_digest else [],
    }

    return (
        "You are OpenClaw, a direct study coach integrated into the StudyClaw app. "
        "Answer the user's question using the provided session metrics. "
        "Be concise, practical, and specific to the session.\n\n"
        f"USER MESSAGE:\n{message}\n\n"
        "CURRENT SESSION SUMMARY:\n"
        f"{json.dumps(summary_payload, indent=2)}\n\n"
        "RECENT HISTORY DIGEST:\n"
        f"{json.dumps(history_payload, indent=2)}"
    )


def _extract_json_payload(output: str) -> dict[str, Any]:
    candidates = _find_json_object_candidates(output)
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    raise RuntimeError(f"Could not parse OpenClaw JSON output:\n{output}")


def _extract_openclaw_text(payload: dict[str, Any]) -> str:
    texts = [item.get("text", "").strip() for item in payload.get("payloads", []) if item.get("text")]
    if not texts:
        raise RuntimeError("OpenClaw returned no text payload.")
    return "\n\n".join(texts)


def _split_command(command: str) -> list[str]:
    try:
        if os.name == "nt":
            return _split_windows_command(command)
        return shlex.split(command, posix=True)
    except ValueError as error:
        raise RuntimeError(f"Invalid OpenClaw command configuration: {error}") from error


def _split_windows_command(command: str) -> list[str]:
    argc = c_int()
    windll.shell32.CommandLineToArgvW.argtypes = [LPCWSTR, POINTER(c_int)]
    windll.shell32.CommandLineToArgvW.restype = POINTER(LPWSTR)
    argv = windll.shell32.CommandLineToArgvW(LPCWSTR(command), byref(argc))
    if not argv:
        raise ValueError("could not parse Windows command line")
    try:
        return [argv[index] for index in range(argc.value)]
    finally:
        windll.kernel32.LocalFree(argv)


def _find_json_object_candidates(output: str) -> list[str]:
    decoder = json.JSONDecoder()
    candidates: list[str] = []
    index = 0
    while index < len(output):
        if output[index] != "{":
            index += 1
            continue
        try:
            _parsed, end = decoder.raw_decode(output[index:])
        except json.JSONDecodeError:
            index += 1
            continue
        candidates.append(output[index : index + end])
        index += end
    return candidates


def _build_recurring_patterns(summaries: list[dict[str, Any]]) -> list[str]:
    patterns: list[str] = []
    if not summaries:
        return patterns

    average_focus = round(
        sum(summary.get("focus_score") or 0 for summary in summaries) / len(summaries),
        1,
    )
    patterns.append(f"Recent sessions averaged a focus score of {average_focus}.")

    recurring_distractions: dict[str, int] = {}
    for summary in summaries:
        for domain in summary.get("top_distraction_domains", []):
            domain_name = domain.get("domain")
            if not domain_name:
                continue
            recurring_distractions[domain_name] = recurring_distractions.get(domain_name, 0) + 1

    if recurring_distractions:
        top_domain = sorted(recurring_distractions.items(), key=lambda item: (-item[1], item[0]))[0][0]
        patterns.append(f"The most common distraction domain has been {top_domain}.")

    return patterns


def _generate_placeholder_chat_response(context: dict[str, Any] | None, message: str) -> dict[str, Any]:
    current_session = context.get("current_session") if context else None
    recent_history = context.get("recent_history_digest") if context else None
    session_meta = context.get("session") if context else {}
    course = session_meta.get("course") or "this session"
    interval_count = current_session.get("interval_count") if current_session else 0
    total_minutes = current_session.get("actual_duration_minutes") if current_session else 0
    sessions_considered = recent_history.get("sessions_considered") if recent_history else 0

    content = (
        "OpenClaw is not connected yet, but the handoff contract is ready. "
        f"I received your message about \"{message}\" with context for {course}. "
        f"The current session includes {interval_count} captured intervals across about {total_minutes} minutes, "
        f"and the backend also prepared a recent-history digest spanning {sessions_considered} prior sessions. "
        "Once the agent is wired in, this same endpoint can forward the structured session summary and history digest "
        "directly into the OpenClaw coaching layer."
    )

    return {
        "role": "assistant",
        "content": content,
        "context": {
            "session_id": context.get("session_id") if context else None,
            "agent_mode": "placeholder",
            "history_sessions_considered": sessions_considered,
        },
    }
