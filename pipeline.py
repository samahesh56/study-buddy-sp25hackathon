"""
StudyClaw Pipeline
==================
Ingest raw telemetry batches, classify intervals via an LLM,
compute per-session metrics, and write everything to Supabase.

Requirements:
    pip install supabase anthropic (replace with chatgpt)

Usage:
    from pipeline import process_batch
    process_batch(batch_json, assignment_name="CMPSC 461 HW3",
                  assignment_desc="Write a recursive descent parser in Python")
"""

import json
import os
from datetime import datetime, timezone

from supabase import create_client, Client
from anthropic import Anthropic # replace with chagpt 

# ── Configuration ──────────────────────────────────────────────

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]  # use service role for backend writes
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "") # replace with gpt 

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
llm = Anthropic(api_key=ANTHROPIC_API_KEY)

# The model used for classification. Sonnet is fast, cheap, and
# accurate enough for binary relevance judgments on short context.
CLASSIFY_MODEL = "claude-sonnet-4-20250514"


# ── Step 1: Ingest ─────────────────────────────────────────────

def ingest_batch(batch: dict) -> list[dict]:
    """
    Insert raw interval events into the `intervals` table.
    Returns the list of event dicts for downstream processing.
    """
    rows = []
    for evt in batch["events"]:
        row = {
            "event_id":              evt["event_id"],
            "session_id":           evt["session_id"],
            "user_id":              evt.get("user_id"),
            "batch_id":             batch.get("batch_id"),
            "interval_start":       evt["interval_start"],
            "interval_end":         evt["interval_end"],
            "duration_ms":          evt["duration_ms"],
            "tab_url":              evt.get("tab_url"),
            "tab_domain":           evt.get("tab_domain"),
            "tab_title":            evt.get("tab_title"),
            "tab_id":               evt.get("tab_id"),
            "window_id":            evt.get("window_id"),
            "is_browser_focused":   evt.get("is_browser_focused", True),
            "is_tab_active":        evt.get("is_tab_active", True),
            "page_visible":         evt.get("page_visible"),
            "scroll_count":         evt.get("scroll_count", 0),
            "click_count":          evt.get("click_count", 0),
            "keystroke_count":      evt.get("keystroke_count", 0),
            "transition_in_reason": evt.get("transition_in_reason"),
            "transition_out_reason":evt.get("transition_out_reason"),
            "segment_index":        evt.get("segment_index"),
            "is_partial_segment":   evt.get("is_partial_segment", False),
        }
        rows.append(row)

    # Upsert to handle duplicate event_ids (deduplication)
    supabase.table("intervals").upsert(rows, on_conflict="event_id").execute()
    return rows


# ── Step 2: LLM Classification ────────────────────────────────

def classify_intervals(
    events: list[dict],
    assignment_name: str,
    assignment_desc: str = "",
) -> list[dict]:
    """
    Send intervals to the LLM for on-task / off-task classification.

    Returns a list of {event_id, relevance, reasoning} dicts.
    """

    # Build the interval summary the LLM will classify.
    # We deliberately send minimal fields to keep token cost low and
    # avoid leaking unnecessary browsing data to the model.
    interval_lines = []
    for evt in events:
        interval_lines.append(
            f"- event_id: {evt['event_id']}  "
            f"url: {evt.get('tab_url', '')}  "
            f"domain: {evt.get('tab_domain', '')}  "
            f"title: {evt.get('tab_title', '')}"
        )
    interval_block = "\n".join(interval_lines)

    # ── The classification prompt ──
    # Kept deliberately simple: a clear task description, the
    # assignment context, and a strict output format.
    prompt = f"""You are classifying browsing activity during a study session.

ASSIGNMENT: {assignment_name}
{f"DESCRIPTION: {assignment_desc}" if assignment_desc else ""}

For each browser interval below, classify whether the page is
ON-TASK (directly relevant to the assignment) or OFF-TASK.

Guidelines:
- Course-specific pages (LMS, assignment page, relevant docs) → on-task
- General reference that clearly supports the assignment topic → on-task
- Social media, news, entertainment, unrelated browsing → off-task
- Ambiguous cases (e.g. Stack Overflow): decide based on whether the
  page title / URL path plausibly relates to the assignment topic

Respond with ONLY a JSON array. Each element must have:
  event_id  (string)  — the interval's event_id
  relevance (number)  — 1.0 if on-task, 0.0 if off-task
  reasoning (string)  — one sentence explaining the classification

INTERVALS:
{interval_block}"""

    response = llm.messages.create(
        model=CLASSIFY_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    # Parse the LLM response
    raw = response.content[0].text.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
    classifications = json.loads(raw)

    # Write classifications back to the intervals table
    now = datetime.now(timezone.utc).isoformat()
    for c in classifications:
        supabase.table("intervals").update({
            "relevance":     c["relevance"],
            "llm_reasoning": c["reasoning"],
            "classified_at": now,
        }).eq("event_id", c["event_id"]).execute()

    return classifications


# ── Step 3: Compute Session Metrics ────────────────────────────

def compute_session_metrics(session_id: str) -> dict:
    """
    Pull all classified intervals for a session and compute the
    per-session metric row.

    METRIC JUSTIFICATIONS
    ---------------------
    task_adherence_ratio
        On-task duration / total duration.
        Ravizza et al. (2017) demonstrated that this ratio significantly
        predicts exam performance even after controlling for prior ability
        (ACT scores, GPA). Kraushaar & Novak (2010) corroborated that the
        inverse (off-task ratio) negatively predicts course GPA.
        → Uses: duration_ms + LLM relevance classification

    active_distraction_ms / active_distraction_ratio
        Off-task time where the student was actively interacting with the
        distracting content (scrolling, clicking, typing).
        Cetintas et al. (2010) showed that interaction features improve
        off-task detection accuracy beyond timing features alone. A student
        actively scrolling Reddit is behaviorally distinct from one who
        left a YouTube tab open in the background.
        → Uses: duration_ms + relevance + scroll/click/keystroke counts

    focus_ratio
        Duration where the browser was the focused window AND the tracked
        tab was active, over total session time. This captures whether the
        student's attention was on the browser at all — complementary to
        task_adherence_ratio which captures *what* they were looking at.
        → Uses: is_browser_focused, is_tab_active, duration_ms

    interaction_density
        Total interactions (scroll + click + keystroke) per second of
        session time. Higher density generally indicates active engagement
        rather than passive consumption or idle time.
        → Uses: scroll_count, click_count, keystroke_count, duration_ms

    context_switches_per_min
        Number of tab or navigation transitions per minute. Frequent
        switching is associated with lower sustained attention and is a
        proxy for multitasking behavior independent of what sites are
        being visited.
        → Uses: transition_in_reason, duration_ms

    longest_on_task_streak_ms
        The longest consecutive run of on-task intervals (by time order).
        Captures sustained deep-work episodes vs fragmented attention.
        → Uses: interval ordering + relevance classification
    """

    # Fetch all intervals for this session, ordered by start time
    result = (
        supabase.table("intervals")
        .select("*")
        .eq("session_id", session_id)
        .order("interval_start")
        .execute()
    )
    intervals = result.data
    if not intervals:
        return {}

    # ── Aggregation ──

    total_ms = 0
    on_task_ms = 0
    off_task_ms = 0
    active_distraction_ms = 0
    passive_distraction_ms = 0
    focused_ms = 0
    total_interactions = 0
    context_switches = 0
    domains = set()

    # Streak tracking
    current_streak_ms = 0
    current_streak_type = None  # True = on-task, False = off-task
    longest_on_task_streak = 0
    longest_off_task_streak = 0

    for iv in intervals:
        dur = iv["duration_ms"]
        total_ms += dur

        is_on_task = (iv.get("relevance") or 0) >= 0.5
        interactions = (
            (iv.get("scroll_count") or 0)
            + (iv.get("click_count") or 0)
            + (iv.get("keystroke_count") or 0)
        )
        total_interactions += interactions

        if is_on_task:
            on_task_ms += dur
        else:
            off_task_ms += dur
            if interactions > 0:
                active_distraction_ms += dur
            else:
                passive_distraction_ms += dur

        if iv.get("is_browser_focused") and iv.get("is_tab_active"):
            focused_ms += dur

        if iv.get("tab_domain"):
            domains.add(iv["tab_domain"])

        # Count context switches
        reason_in = iv.get("transition_in_reason", "")
        if reason_in in ("tab_activated", "navigation_completed"):
            context_switches += 1

        # Streak logic
        if current_streak_type == is_on_task:
            current_streak_ms += dur
        else:
            # Save previous streak
            if current_streak_type is True:
                longest_on_task_streak = max(longest_on_task_streak, current_streak_ms)
            elif current_streak_type is False:
                longest_off_task_streak = max(longest_off_task_streak, current_streak_ms)
            current_streak_ms = dur
            current_streak_type = is_on_task

    # Final streak
    if current_streak_type is True:
        longest_on_task_streak = max(longest_on_task_streak, current_streak_ms)
    elif current_streak_type is False:
        longest_off_task_streak = max(longest_off_task_streak, current_streak_ms)

    total_s = max(total_ms / 1000, 0.001)  # avoid division by zero
    total_min = total_s / 60
    n_intervals = len(intervals)

    metrics = {
        "session_id":               session_id,
        "user_id":                  intervals[0].get("user_id"),

        "total_duration_ms":        total_ms,
        "on_task_duration_ms":      on_task_ms,
        "off_task_duration_ms":     off_task_ms,
        "task_adherence_ratio":     round(on_task_ms / max(total_ms, 1), 4),

        "active_distraction_ms":    active_distraction_ms,
        "passive_distraction_ms":   passive_distraction_ms,
        "active_distraction_ratio": round(
            active_distraction_ms / max(off_task_ms, 1), 4
        ),

        "focused_duration_ms":      focused_ms,
        "focus_ratio":              round(focused_ms / max(total_ms, 1), 4),
        "interaction_density":      round(total_interactions / total_s, 4),
        "mean_interval_interactions": round(total_interactions / max(n_intervals, 1), 2),

        "context_switch_count":     context_switches,
        "context_switches_per_min": round(context_switches / max(total_min, 0.001), 4),
        "unique_domains":           len(domains),

        "longest_on_task_streak_ms":  longest_on_task_streak,
        "longest_off_task_streak_ms": longest_off_task_streak,

        "total_intervals":          n_intervals,
        "on_task_intervals":        sum(1 for iv in intervals if (iv.get("relevance") or 0) >= 0.5),
        "off_task_intervals":       sum(1 for iv in intervals if (iv.get("relevance") or 0) < 0.5),
    }

    # Upsert into session_metrics
    supabase.table("session_metrics").upsert(
        metrics, on_conflict="session_id"
    ).execute()

    return metrics


# ── Orchestrator ───────────────────────────────────────────────

def process_batch(
    batch: dict,
    assignment_name: str,
    assignment_desc: str = "",
) -> dict:
    """
    Full pipeline: ingest → classify → compute metrics.

    Parameters
    ----------
    batch : dict
        A raw telemetry batch from the Chrome extension.
    assignment_name : str
        Short name of the assignment (e.g. "CMPSC 461 HW3").
    assignment_desc : str, optional
        Longer description for better LLM context
        (e.g. "Write a recursive descent parser in Python").

    Returns
    -------
    dict with keys: session_id, classifications, metrics
    """
    session_id = batch["session_id"]

    # Ensure session row exists
    supabase.table("sessions").upsert({
        "session_id":      session_id,
        "user_id":         batch.get("user_id"),
        "assignment_name": assignment_name,
        "assignment_desc": assignment_desc,
    }, on_conflict="session_id").execute()

    # 1. Ingest raw intervals
    events = ingest_batch(batch)

    # 2. Classify with LLM
    classifications = classify_intervals(events, assignment_name, assignment_desc)

    # 3. Compute session-level metrics
    metrics = compute_session_metrics(session_id)

    return {
        "session_id":      session_id,
        "classifications": classifications,
        "metrics":         metrics,
    }


# ── CLI Usage ──────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python pipeline.py <batch.json> <assignment_name> [assignment_desc]")
        sys.exit(1)

    batch_path = sys.argv[1]
    a_name = sys.argv[2]
    a_desc = sys.argv[3] if len(sys.argv) > 3 else ""

    with open(batch_path) as f:
        batch_data = json.load(f)

    result = process_batch(batch_data, a_name, a_desc)
    print(json.dumps(result, indent=2))