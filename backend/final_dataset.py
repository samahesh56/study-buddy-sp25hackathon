from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from backend.storage import Storage


PRODUCTIVE_DOMAINS = {
    "docs.google.com",
    "drive.google.com",
    "github.com",
    "stackoverflow.com",
    "wikipedia.org",
}

DISTRACTING_DOMAINS = {
    "reddit.com",
    "youtube.com",
    "netflix.com",
    "hulu.com",
    "instagram.com",
    "tiktok.com",
    "x.com",
    "twitter.com",
    "discord.com",
    "twitch.tv",
}

INTERNAL_DOMAINS = {
    "127.0.0.1",
    "localhost",
    "extensions",
    "newtab",
}


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def iso_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def overlap_seconds(
    left_start: datetime,
    left_end: datetime,
    right_start: datetime,
    right_end: datetime,
) -> float:
    start = max(left_start, right_start)
    end = min(left_end, right_end)
    return max(0.0, (end - start).total_seconds())


def normalize_domain_value(value: str | None) -> str | None:
    if not value:
        return None
    domain = value.strip().lower()
    if "://" in domain:
        domain = domain.split("://", 1)[1]
    domain = domain.split("/", 1)[0]
    if domain.startswith("www."):
        domain = domain[4:]
    return domain or None


@dataclass
class CameraWindow:
    start_at: datetime
    end_at: datetime
    attention_state: str
    camera_focus_score: float
    camera_focus_label: str
    face_present_ratio: float
    screen_attention_ratio: float
    phone_candidate_ratio: float
    likely_phone_use: bool
    lookaway_events: int
    blink_count: int
    long_eye_closure_count: int


@dataclass
class CameraSessionArtifact:
    camera_session_id: str
    started_at: datetime
    ended_at: datetime
    graph_path: Path | None
    distraction_images: list[Path]
    windows: list[CameraWindow]
    transitions_report: dict[str, Any]
    snapshots_report: dict[str, Any]


@dataclass
class CameraSummaryMetrics:
    focus_score: float | None
    face_present_ratio: float | None
    screen_attention_ratio: float | None
    phone_usage_ratio: float | None
    away_ratio: float | None
    semi_focused_ratio: float | None
    blink_count: int
    distraction_event_count: int
    away_event_count: int
    distraction_window_count: int
    distraction_image_count: int


class FinalDatasetService:
    def __init__(self, storage: Storage, camera_data_dir: str | None = None) -> None:
        self.storage = storage
        self.camera_data_dir = Path(camera_data_dir) if camera_data_dir else None

    def list_sessions(self) -> list[dict[str, Any]]:
        sessions = self.storage.list_sessions()
        return [self.get_enriched_session(session["session_id"], session=session) for session in sessions]

    def get_enriched_session(self, session_id: str, session: dict[str, Any] | None = None) -> dict[str, Any] | None:
        session = session or self.storage.get_session(session_id)
        if not session:
            return None

        summary = self.get_session_summary(session_id, session=session)
        if not summary:
            return session
        return {
            **session,
            "actual_duration_minutes": summary["actual_duration_minutes"],
            "focus_score": summary["focus_score"],
            "on_task_ratio": summary["on_task_ratio"],
            "off_task_ratio": summary["off_task_ratio"],
            "away_ratio": summary["away_ratio"],
            "distraction_event_count": summary["distraction_event_count"],
            "camera_session_id": summary.get("camera_session_id"),
        }

    def get_session_summary(self, session_id: str, session: dict[str, Any] | None = None) -> dict[str, Any] | None:
        final_dataset = self.get_final_dataset(session_id, session=session)
        return final_dataset["summary"] if final_dataset else None

    def get_final_dataset(self, session_id: str, session: dict[str, Any] | None = None) -> dict[str, Any] | None:
        session = session or self.storage.get_session(session_id)
        if not session:
            return None

        browser_intervals = self.storage.list_session_intervals(session_id)
        top_domains = self._compute_top_domains(browser_intervals)
        camera_artifact = self._match_camera_artifact(session, browser_intervals)
        merged_segments = self._build_merged_segments(
            session=session,
            browser_intervals=browser_intervals,
            camera_artifact=camera_artifact,
        )

        summary = self._build_summary(
            session=session,
            browser_intervals=browser_intervals,
            merged_segments=merged_segments,
            top_domains=top_domains,
            camera_artifact=camera_artifact,
        )
        enriched_session = {
            **session,
            "actual_duration_minutes": summary["actual_duration_minutes"],
            "focus_score": summary["focus_score"],
            "on_task_ratio": summary["on_task_ratio"],
            "off_task_ratio": summary["off_task_ratio"],
            "away_ratio": summary["away_ratio"],
            "distraction_event_count": summary["distraction_event_count"],
            "camera_session_id": summary.get("camera_session_id"),
        }
        return {
            "session": enriched_session,
            "summary": summary,
            "segments": merged_segments,
            "camera_artifact": {
                "camera_session_id": camera_artifact.camera_session_id,
                "started_at": iso_or_none(camera_artifact.started_at),
                "ended_at": iso_or_none(camera_artifact.ended_at),
                "graph_path": str(camera_artifact.graph_path) if camera_artifact and camera_artifact.graph_path else None,
                "distraction_images": [
                    self._build_distraction_image_payload(session["session_id"], image_path)
                    for image_path in camera_artifact.distraction_images
                ],
            }
            if camera_artifact
            else None,
        }

    def get_session_graph_path(self, session_id: str) -> Path | None:
        final_dataset = self.get_final_dataset(session_id)
        camera_artifact = final_dataset.get("camera_artifact") if final_dataset else None
        if not camera_artifact or not camera_artifact.get("graph_path"):
            return None
        path = Path(camera_artifact["graph_path"])
        return path if path.exists() else None

    def get_session_distraction_image_paths(self, session_id: str) -> dict[str, Path]:
        final_dataset = self.get_final_dataset(session_id)
        camera_artifact = final_dataset.get("camera_artifact") if final_dataset else None
        if not camera_artifact:
            return {}

        image_paths: dict[str, Path] = {}
        for item in camera_artifact.get("distraction_images", []):
            image_path = Path(item["path"])
            if image_path.exists():
                image_paths[item["filename"]] = image_path
        return image_paths

    def _build_summary(
        self,
        session: dict[str, Any],
        browser_intervals: list[dict[str, Any]],
        merged_segments: list[dict[str, Any]],
        top_domains: list[dict[str, Any]],
        camera_artifact: CameraSessionArtifact | None,
    ) -> dict[str, Any]:
        total_duration_ms = sum(int(interval.get("duration_ms") or 0) for interval in browser_intervals)
        total_duration_minutes = round(total_duration_ms / 60000.0)
        total_duration_seconds = total_duration_ms / 1000.0 if total_duration_ms else 0.0
        camera_metrics = _derive_camera_summary_metrics(camera_artifact)

        durations_by_label: dict[str, float] = defaultdict(float)
        relevant_domain_seconds: dict[str, float] = defaultdict(float)
        distracting_domain_seconds: dict[str, float] = defaultdict(float)
        focus_streaks: list[float] = []
        recovery_windows: list[float] = []
        current_focus_streak = 0.0
        current_bad_run = 0.0
        previous_label: str | None = None
        tab_switch_count = 0
        relevant_to_irrelevant_switch_count = 0
        irrelevant_to_relevant_switch_count = 0
        merged_distraction_event_count = 0
        merged_away_event_count = 0
        active_on_task_seconds = 0.0
        passive_on_task_seconds = 0.0

        for segment in merged_segments:
            duration_seconds = segment["duration_ms"] / 1000.0
            label = segment["merged_productivity_label"]
            durations_by_label[label] += duration_seconds

            if segment["browser_transition_in_reason"] in {"tab_activated", "navigation_completed"}:
                tab_switch_count += 1

            if label == "on_task":
                if segment["interaction_count"] > 0:
                    active_on_task_seconds += duration_seconds
                else:
                    passive_on_task_seconds += duration_seconds
                current_focus_streak += duration_seconds
                if current_bad_run > 0:
                    recovery_windows.append(current_bad_run)
                    current_bad_run = 0.0
            else:
                if current_focus_streak > 0:
                    focus_streaks.append(current_focus_streak)
                    current_focus_streak = 0.0
                if label in {"off_task", "away", "phone"}:
                    current_bad_run += duration_seconds

            if label in {"off_task", "away", "phone"} and previous_label != label:
                merged_distraction_event_count += 1
            if label == "away" and previous_label != "away":
                merged_away_event_count += 1
            if previous_label == "on_task" and label in {"off_task", "away", "phone"}:
                relevant_to_irrelevant_switch_count += 1
            if previous_label in {"off_task", "away", "phone"} and label == "on_task":
                irrelevant_to_relevant_switch_count += 1
            previous_label = label

            domain = segment["browser_domain"]
            if domain and domain not in INTERNAL_DOMAINS and label == "on_task":
                relevant_domain_seconds[domain] += duration_seconds
            if domain and domain not in INTERNAL_DOMAINS and label in {"off_task", "phone"}:
                distracting_domain_seconds[domain] += duration_seconds

        if current_focus_streak > 0:
            focus_streaks.append(current_focus_streak)

        on_task_ratio = _safe_ratio(durations_by_label["on_task"], total_duration_seconds)
        off_task_ratio = _safe_ratio(
            durations_by_label["off_task"] + durations_by_label["phone"],
            total_duration_seconds,
        )
        away_ratio = _safe_ratio(durations_by_label["away"], total_duration_seconds)
        unknown_ratio = _safe_ratio(durations_by_label["unknown"], total_duration_seconds)

        if camera_metrics.focus_score is not None:
            focus_score = round(camera_metrics.focus_score, 1)
        else:
            focus_score = round(max(0.0, 100.0 * on_task_ratio - 25.0 * off_task_ratio), 1)

        if camera_metrics.away_ratio is not None:
            away_ratio = round(camera_metrics.away_ratio, 3)

        graph_image_url = None
        if camera_artifact and camera_artifact.graph_path and camera_artifact.graph_path.exists():
            graph_image_url = f"/sessions/{session['session_id']}/graph.png"
        distraction_images = []
        if camera_artifact:
            distraction_images = [
                self._build_distraction_image_payload(session["session_id"], image_path)
                for image_path in camera_artifact.distraction_images
            ]

        top_relevant_domains = _ranked_domains(relevant_domain_seconds)
        top_distraction_domains = _ranked_domains(distracting_domain_seconds)
        camera_state_summary = (
            camera_artifact.transitions_report.get("state_summary", {})
            if camera_artifact
            else {}
        )
        if camera_artifact and camera_artifact.windows:
            distraction_event_count = camera_metrics.distraction_event_count
            away_event_count = camera_metrics.away_event_count
        else:
            distraction_event_count = merged_distraction_event_count
            away_event_count = merged_away_event_count

        return {
            "session_id": session["session_id"],
            "session": session,
            "interval_count": len(browser_intervals),
            "total_duration_ms": total_duration_ms,
            "actual_duration_minutes": total_duration_minutes,
            "planned_duration_minutes": session.get("planned_duration_minutes") or 0,
            "focus_score": focus_score,
            "on_task_ratio": round(on_task_ratio, 3),
            "off_task_ratio": round(off_task_ratio, 3),
            "away_ratio": round(away_ratio, 3),
            "unknown_ratio": round(unknown_ratio, 3),
            "active_on_task_minutes": round(active_on_task_seconds / 60.0, 1),
            "passive_on_task_minutes": round(passive_on_task_seconds / 60.0, 1),
            "off_task_minutes": round((durations_by_label["off_task"] + durations_by_label["phone"]) / 60.0, 1),
            "idle_minutes": round((durations_by_label["away"] + durations_by_label["unknown"]) / 60.0, 1),
            "longest_focus_streak_minutes": round(max(focus_streaks, default=0.0) / 60.0, 1),
            "average_focus_streak_minutes": round((sum(focus_streaks) / len(focus_streaks) / 60.0), 1)
            if focus_streaks
            else 0.0,
            "tab_switch_count": tab_switch_count,
            "relevant_to_irrelevant_switch_count": relevant_to_irrelevant_switch_count,
            "irrelevant_to_relevant_switch_count": irrelevant_to_relevant_switch_count,
            "distraction_event_count": distraction_event_count,
            "average_recovery_time_seconds": round(sum(recovery_windows) / len(recovery_windows), 1)
            if recovery_windows
            else 0.0,
            "screen_attention_ratio": round(camera_metrics.screen_attention_ratio, 3)
            if camera_metrics.screen_attention_ratio is not None
            else 0.0,
            "face_present_ratio": round(camera_metrics.face_present_ratio, 3)
            if camera_metrics.face_present_ratio is not None
            else 0.0,
            "phone_usage_ratio": round(camera_metrics.phone_usage_ratio, 3)
            if camera_metrics.phone_usage_ratio is not None
            else 0.0,
            "away_event_count": away_event_count,
            "blink_count": camera_metrics.blink_count,
            "camera_distraction_window_count": camera_metrics.distraction_window_count,
            "camera_session_id": camera_artifact.camera_session_id if camera_artifact else None,
            "camera_state_summary": camera_state_summary,
            "top_domains": top_domains,
            "top_relevant_domains": top_relevant_domains,
            "top_distraction_domains": top_distraction_domains,
            "timeline_highlights": _build_timeline_highlights(merged_segments),
            "graph_image_url": graph_image_url,
            "graph_png_url": graph_image_url,
            "graph_image_src": graph_image_url,
            "distraction_images": distraction_images,
            "distraction_image_count": len(distraction_images),
            "system_observations": _build_system_observations(
                browser_intervals=browser_intervals,
                camera_artifact=camera_artifact,
                focus_score=focus_score,
                distraction_event_count=distraction_event_count,
                top_relevant_domains=top_relevant_domains,
                top_distraction_domains=top_distraction_domains,
            ),
            "coaching_report": _build_coaching_report(
                session=session,
                focus_score=focus_score,
                on_task_ratio=on_task_ratio,
                top_relevant_domains=top_relevant_domains,
                top_distraction_domains=top_distraction_domains,
            ),
        }

    def _build_merged_segments(
        self,
        session: dict[str, Any],
        browser_intervals: list[dict[str, Any]],
        camera_artifact: CameraSessionArtifact | None,
    ) -> list[dict[str, Any]]:
        camera_windows = camera_artifact.windows if camera_artifact else []
        segments: list[dict[str, Any]] = []

        for interval in browser_intervals:
            start_at = parse_iso_datetime(interval.get("interval_start"))
            end_at = parse_iso_datetime(interval.get("interval_end"))
            if not start_at or not end_at or end_at <= start_at:
                continue

            overlapping_windows = [
                window
                for window in camera_windows
                if overlap_seconds(start_at, end_at, window.start_at, window.end_at) > 0
            ]
            camera_rollup = _roll_up_camera_windows(overlapping_windows)
            browser_domain = normalize_domain_value(interval.get("normalized_domain") or interval.get("tab_domain"))
            browser_class = _classify_browser_interval(session, interval, browser_domain)
            merged_label = _merge_labels(browser_class, camera_rollup)

            segments.append(
                {
                    "session_id": session["session_id"],
                    "segment_start": iso_or_none(start_at),
                    "segment_end": iso_or_none(end_at),
                    "duration_ms": int(interval.get("duration_ms") or 0),
                    "browser_domain": browser_domain,
                    "browser_title": interval.get("tab_title"),
                    "browser_classification": browser_class,
                    "browser_transition_in_reason": interval.get("transition_in_reason"),
                    "browser_transition_out_reason": interval.get("transition_out_reason"),
                    "interaction_count": int(interval.get("scroll_count") or 0)
                    + int(interval.get("click_count") or 0)
                    + int(interval.get("keystroke_count") or 0),
                    "camera_attention_state": camera_rollup.get("attention_state"),
                    "camera_focus_score": camera_rollup.get("camera_focus_score"),
                    "camera_focus_label": camera_rollup.get("camera_focus_label"),
                    "camera_phone_flag": camera_rollup.get("likely_phone_use"),
                    "face_present_ratio": camera_rollup.get("face_present_ratio"),
                    "screen_attention_ratio": camera_rollup.get("screen_attention_ratio"),
                    "camera_blink_count": camera_rollup.get("blink_count"),
                    "merged_attention_label": camera_rollup.get("attention_state") or "unknown",
                    "merged_productivity_label": merged_label,
                }
            )

        return segments

    def _match_camera_artifact(
        self,
        session: dict[str, Any],
        browser_intervals: list[dict[str, Any]],
    ) -> CameraSessionArtifact | None:
        artifacts = self._load_camera_artifacts()
        if not artifacts:
            return None

        browser_start = parse_iso_datetime(session.get("started_at"))
        browser_end = parse_iso_datetime(session.get("stopped_at"))
        if browser_intervals:
            interval_starts = [
                parsed
                for parsed in (parse_iso_datetime(interval.get("interval_start")) for interval in browser_intervals)
                if parsed
            ]
            interval_ends = [
                parsed
                for parsed in (parse_iso_datetime(interval.get("interval_end")) for interval in browser_intervals)
                if parsed
            ]
            if interval_starts:
                browser_start = min(interval_starts)
            if interval_ends:
                browser_end = max(interval_ends)
        if not browser_start or not browser_end:
            return None

        best_match: tuple[float, float, CameraSessionArtifact] | None = None
        for artifact in artifacts:
            overlap = overlap_seconds(browser_start, browser_end, artifact.started_at, artifact.ended_at)
            start_distance = abs((artifact.started_at - browser_start).total_seconds())
            score = (overlap, -start_distance)
            if overlap <= 0 and start_distance > 1800:
                continue
            if best_match is None or score > (best_match[0], best_match[1]):
                best_match = (score[0], score[1], artifact)

        return best_match[2] if best_match else None

    def _load_camera_artifacts(self) -> list[CameraSessionArtifact]:
        if not self.camera_data_dir or not self.camera_data_dir.exists():
            return []

        artifacts: list[CameraSessionArtifact] = []
        for transitions_path in self.camera_data_dir.rglob("*_transitions.json"):
            camera_session_id = transitions_path.name.removesuffix("_transitions.json")
            session_dir = transitions_path.parent
            snapshots_path = session_dir / f"{camera_session_id}_snapshots.json"
            windows_path = session_dir / f"{camera_session_id}_windows.csv"
            graph_path = session_dir / f"{camera_session_id}_summary.png"
            distracted_dir = session_dir / "distracted"

            try:
                transitions_report = json.loads(transitions_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue

            snapshots_report: dict[str, Any] = {}
            if snapshots_path.exists():
                try:
                    snapshots_report = json.loads(snapshots_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    snapshots_report = {}

            started_at = parse_iso_datetime(transitions_report.get("started_at"))
            ended_at = parse_iso_datetime(transitions_report.get("ended_at"))
            windows = self._load_camera_windows(windows_path, reference_started_at=started_at)
            if not started_at and windows:
                started_at = windows[0].start_at
            if not ended_at and windows:
                ended_at = windows[-1].end_at
            if not started_at or not ended_at:
                continue

            distraction_images = []
            if distracted_dir.exists():
                distraction_images = sorted(distracted_dir.glob("*.png"))

            artifacts.append(
                CameraSessionArtifact(
                    camera_session_id=camera_session_id,
                    started_at=started_at,
                    ended_at=ended_at,
                    graph_path=graph_path if graph_path.exists() else None,
                    distraction_images=distraction_images,
                    windows=windows,
                    transitions_report=transitions_report,
                    snapshots_report=snapshots_report,
                )
            )

        artifacts.sort(key=lambda artifact: artifact.started_at, reverse=True)
        return artifacts

    def _load_camera_windows(
        self,
        windows_path: Path,
        reference_started_at: datetime | None = None,
    ) -> list[CameraWindow]:
        if not windows_path.exists():
            return []

        windows: list[CameraWindow] = []
        with windows_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                end_at = _parse_camera_window_timestamp(
                    row.get("timestamp"),
                    reference_started_at=reference_started_at,
                )
                window_length_sec = _to_float(row.get("window_length_sec"), default=5.0)
                if not end_at:
                    continue
                windows.append(
                    CameraWindow(
                        start_at=end_at - timedelta(seconds=window_length_sec),
                        end_at=end_at,
                        attention_state=(row.get("attention_state") or "AWAY").upper(),
                        camera_focus_score=_to_float(row.get("camera_focus_score")),
                        camera_focus_label=row.get("camera_focus_label") or "N/A",
                        face_present_ratio=_to_float(row.get("face_present_percent")) / 100.0,
                        screen_attention_ratio=_to_float(row.get("looking_forward_percent")) / 100.0,
                        phone_candidate_ratio=_to_float(row.get("phone_candidate_percent")) / 100.0,
                        likely_phone_use=_to_bool(row.get("likely_phone_use")),
                        lookaway_events=int(_to_float(row.get("lookaway_events"))),
                        blink_count=int(_to_float(row.get("blink_count"))),
                        long_eye_closure_count=int(_to_float(row.get("long_eye_closure_count"))),
                    )
                )
        return windows

    def _build_distraction_image_payload(self, session_id: str, image_path: Path) -> dict[str, Any]:
        stem = image_path.stem.removesuffix("_distracted")
        image_timestamp = parse_iso_datetime(stem)
        if not image_timestamp:
            try:
                image_timestamp = datetime.strptime(stem, "%Y-%m-%dT%H-%M-%S").replace(tzinfo=UTC)
            except ValueError:
                image_timestamp = _parse_camera_window_timestamp(stem.replace("T", " "), reference_started_at=None)
        return {
            "filename": image_path.name,
            "path": str(image_path),
            "captured_at": iso_or_none(image_timestamp),
            "url": f"/sessions/{session_id}/distraction-images/{image_path.name}",
        }

    def _compute_top_domains(self, browser_intervals: list[dict[str, Any]]) -> list[dict[str, Any]]:
        totals: dict[str, dict[str, Any]] = {}
        for interval in browser_intervals:
            domain = normalize_domain_value(interval.get("normalized_domain") or interval.get("tab_domain"))
            if not domain:
                continue
            bucket = totals.setdefault(domain, {"domain": domain, "interval_count": 0, "total_duration_ms": 0})
            bucket["interval_count"] += 1
            bucket["total_duration_ms"] += int(interval.get("duration_ms") or 0)
        return sorted(
            totals.values(),
            key=lambda item: (-item["total_duration_ms"], -item["interval_count"], item["domain"]),
        )[:10]


def _classify_browser_interval(session: dict[str, Any], interval: dict[str, Any], domain: str | None) -> str:
    title = (interval.get("tab_title") or "").lower()
    if domain:
        if domain in INTERNAL_DOMAINS:
            return "internal"
        if domain.endswith(".instructure.com"):
            return "productive"
        if any(domain == candidate or domain.endswith(f".{candidate}") for candidate in PRODUCTIVE_DOMAINS):
            return "productive"
        if any(domain == candidate or domain.endswith(f".{candidate}") for candidate in DISTRACTING_DOMAINS):
            return "distracting"

    course = (session.get("course") or "").lower()
    course_tokens = [token for token in _tokenize(course) if len(token) >= 3]
    if course_tokens and any(token in title for token in course_tokens):
        return "productive"

    return "neutral"


def _merge_labels(browser_class: str, camera_rollup: dict[str, Any]) -> str:
    attention_state = camera_rollup.get("attention_state")
    focus_score = camera_rollup.get("camera_focus_score")
    likely_phone_use = camera_rollup.get("likely_phone_use")

    if attention_state == "AWAY":
        return "away"
    if likely_phone_use:
        return "phone"
    if browser_class == "internal":
        return "unknown"
    if browser_class == "distracting":
        return "off_task"
    if browser_class == "productive":
        if focus_score is None or focus_score >= 50:
            return "on_task"
        return "off_task"
    if focus_score is not None:
        if focus_score >= 75 and attention_state in {"FOCUSED", "SEMI_FOCUSED"}:
            return "on_task"
        if focus_score < 50:
            return "off_task"
    return "unknown"


def _roll_up_camera_windows(windows: list[CameraWindow]) -> dict[str, Any]:
    if not windows:
        return {
            "attention_state": None,
            "camera_focus_score": None,
            "camera_focus_label": None,
            "face_present_ratio": None,
            "screen_attention_ratio": None,
            "likely_phone_use": False,
            "blink_count": 0,
        }

    state_counts = Counter(window.attention_state for window in windows)
    label_counts = Counter(window.camera_focus_label for window in windows)
    return {
        "attention_state": state_counts.most_common(1)[0][0],
        "camera_focus_score": round(sum(window.camera_focus_score for window in windows) / len(windows), 1),
        "camera_focus_label": label_counts.most_common(1)[0][0],
        "face_present_ratio": round(sum(window.face_present_ratio for window in windows) / len(windows), 3),
        "screen_attention_ratio": round(sum(window.screen_attention_ratio for window in windows) / len(windows), 3),
        "likely_phone_use": any(window.likely_phone_use for window in windows),
        "blink_count": sum(window.blink_count for window in windows),
    }


def _build_timeline_highlights(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    highlights = []
    for segment in segments:
        if segment["merged_productivity_label"] in {"away", "phone"}:
            highlights.append(
                {
                    "start": segment["segment_start"],
                    "end": segment["segment_end"],
                    "label": segment["merged_productivity_label"],
                    "domain": segment["browser_domain"],
                }
            )
    return highlights[:8]


def _build_system_observations(
    browser_intervals: list[dict[str, Any]],
    camera_artifact: CameraSessionArtifact | None,
    focus_score: float,
    distraction_event_count: int,
    top_relevant_domains: list[dict[str, Any]],
    top_distraction_domains: list[dict[str, Any]],
) -> list[str]:
    observations = [
        f"Browser telemetry contributed {len(browser_intervals)} intervals to the merged session dataset.",
        f"The merged focus score for this session is {focus_score:.1f}.",
    ]
    if camera_artifact:
        observations.append(
            f"Camera attention data was matched from session artifact {camera_artifact.camera_session_id}."
        )
        observations.append(
            f"Computer vision detected {distraction_event_count} distraction period(s) across the session."
        )
    else:
        observations.append("No matching camera artifact was found, so browser-only heuristics filled the gaps.")
    if top_relevant_domains:
        observations.append(f"Most productive domain: {top_relevant_domains[0]['domain']}.")
    if top_distraction_domains:
        observations.append(f"Top distraction domain: {top_distraction_domains[0]['domain']}.")
    return observations


def _build_coaching_report(
    session: dict[str, Any],
    focus_score: float,
    on_task_ratio: float,
    top_relevant_domains: list[dict[str, Any]],
    top_distraction_domains: list[dict[str, Any]],
) -> str:
    course = session.get("course") or "this session"
    productive = top_relevant_domains[0]["domain"] if top_relevant_domains else "your productive tools"
    distraction = top_distraction_domains[0]["domain"] if top_distraction_domains else "unclassified distractions"
    return (
        f"For {course}, the merged browser and camera dataset estimated a focus score of {focus_score:.1f} "
        f"with about {round(on_task_ratio * 100)}% of captured browser time classified as on-task. "
        f"Your strongest productive signal came from {productive}. "
        f"The main distraction signal came from {distraction}. "
        "This report is generated from the current heuristic dataset layer and is designed to be replaced by "
        "a stronger analytics pipeline later without changing the app contract."
    )


def _ranked_domains(domain_seconds: dict[str, float]) -> list[dict[str, Any]]:
    return [
        {
            "domain": domain,
            "total_duration_ms": int(seconds * 1000),
        }
        for domain, seconds in sorted(domain_seconds.items(), key=lambda item: (-item[1], item[0]))[:5]
    ]


def _safe_ratio(value: float, total: float) -> float:
    if total <= 0:
        return 0.0
    return value / total


def _tokenize(value: str) -> list[str]:
    return [token for token in "".join(char if char.isalnum() else " " for char in value).split() if token]


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes"}


def _derive_camera_summary_metrics(camera_artifact: CameraSessionArtifact | None) -> CameraSummaryMetrics:
    if not camera_artifact or not camera_artifact.windows:
        distraction_image_count = len(camera_artifact.distraction_images) if camera_artifact else 0
        return CameraSummaryMetrics(
            focus_score=None,
            face_present_ratio=None,
            screen_attention_ratio=None,
            phone_usage_ratio=None,
            away_ratio=None,
            semi_focused_ratio=None,
            blink_count=int(camera_artifact.transitions_report.get("total_blinks", 0)) if camera_artifact else 0,
            distraction_event_count=0,
            away_event_count=0,
            distraction_window_count=0,
            distraction_image_count=distraction_image_count,
        )

    windows = camera_artifact.windows
    total_window_seconds = sum((window.end_at - window.start_at).total_seconds() for window in windows) or 1.0

    def weighted_average(getter):
        weighted_total = 0.0
        for window in windows:
            duration = (window.end_at - window.start_at).total_seconds()
            weighted_total += getter(window) * duration
        return weighted_total / total_window_seconds

    distraction_window_count = sum(1 for window in windows if _is_distracting_window(window))
    distraction_event_count = _count_window_runs(windows, _is_distracting_window)
    away_event_count = _count_window_runs(windows, lambda window: window.attention_state == "AWAY")
    state_summary = camera_artifact.transitions_report.get("state_summary", {})
    away_ratio = _state_percent_ratio(state_summary, "AWAY")
    semi_focused_ratio = _state_percent_ratio(state_summary, "SEMI_FOCUSED")
    return CameraSummaryMetrics(
        focus_score=weighted_average(lambda window: window.camera_focus_score),
        face_present_ratio=weighted_average(lambda window: window.face_present_ratio),
        screen_attention_ratio=weighted_average(lambda window: window.screen_attention_ratio),
        phone_usage_ratio=weighted_average(lambda window: 1.0 if window.likely_phone_use else window.phone_candidate_ratio),
        away_ratio=away_ratio,
        semi_focused_ratio=semi_focused_ratio,
        blink_count=int(camera_artifact.transitions_report.get("total_blinks", 0)),
        distraction_event_count=distraction_event_count,
        away_event_count=away_event_count,
        distraction_window_count=distraction_window_count,
        distraction_image_count=len(camera_artifact.distraction_images),
    )


def _is_distracting_window(window: CameraWindow) -> bool:
    return (
        window.attention_state in {"AWAY", "SEMI_FOCUSED"}
        or window.likely_phone_use
        or window.camera_focus_score < 50.0
        or window.camera_focus_label.strip().lower() == "distracted"
    )


def _count_window_runs(windows: list[CameraWindow], predicate) -> int:
    run_count = 0
    in_run = False
    for window in windows:
        if predicate(window):
            if not in_run:
                run_count += 1
                in_run = True
        else:
            in_run = False
    return run_count


def _state_percent_ratio(state_summary: dict[str, Any], state_name: str) -> float | None:
    state = state_summary.get(state_name)
    if not state:
        return None
    return _to_float(state.get("percent")) / 100.0


def _parse_camera_window_timestamp(
    value: str | None,
    reference_started_at: datetime | None,
) -> datetime | None:
    if not value:
        return None

    normalized = value.strip()
    has_timezone = (
        normalized.endswith("Z")
        or "+" in normalized[10:]
        or "-" in normalized[10:]
    )
    if has_timezone:
        return parse_iso_datetime(normalized)

    normalized = normalized.replace(" ", "T")
    try:
        naive = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    local_tz = datetime.now().astimezone().tzinfo or UTC
    local_candidate = naive.replace(tzinfo=local_tz).astimezone(UTC)
    utc_candidate = naive.replace(tzinfo=UTC)

    if reference_started_at is None:
        return local_candidate

    local_delta = abs((local_candidate - reference_started_at).total_seconds())
    utc_delta = abs((utc_candidate - reference_started_at).total_seconds())
    return local_candidate if local_delta <= utc_delta else utc_candidate
