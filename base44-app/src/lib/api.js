const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

async function request(path, options = {}) {
    const response = await fetch(`${API_BASE}${path}`, {
        headers: {
            "Content-Type": "application/json",
            ...(options.headers || {}),
        },
        ...options,
    });

    if (!response.ok) {
        const text = await response.text();
        throw new Error(`${response.status} ${response.statusText}: ${text}`);
    }

    return response.json();
}

function normalizeSession(session) {
    if (!session) return null;
    return {
        ...session,
        actual_duration_minutes: session.actual_duration_minutes ?? 0,
        focus_score: session.focus_score ?? null,
        on_task_ratio: session.on_task_ratio ?? null,
    };
}

function buildSummaryFallback(session, summary) {
    const totalDurationMinutes = Math.round((summary.total_duration_ms || 0) / 60000);
    return {
        session_id: session?.session_id,
        planned_duration_minutes: session?.planned_duration_minutes ?? 0,
        actual_duration_minutes: totalDurationMinutes,
        focus_score: summary.focus_score ?? null,
        on_task_ratio: summary.on_task_ratio ?? 0,
        off_task_ratio: summary.off_task_ratio ?? 0,
        unknown_ratio: summary.unknown_ratio ?? 1,
        active_on_task_minutes: summary.active_on_task_minutes ?? 0,
        passive_on_task_minutes: summary.passive_on_task_minutes ?? 0,
        off_task_minutes: summary.off_task_minutes ?? 0,
        idle_minutes: summary.idle_minutes ?? 0,
        longest_focus_streak_minutes: summary.longest_focus_streak_minutes ?? 0,
        average_focus_streak_minutes: summary.average_focus_streak_minutes ?? 0,
        tab_switch_count: summary.tab_switch_count ?? 0,
        relevant_to_irrelevant_switch_count: summary.relevant_to_irrelevant_switch_count ?? 0,
        irrelevant_to_relevant_switch_count: summary.irrelevant_to_relevant_switch_count ?? 0,
        distraction_event_count: summary.distraction_event_count ?? 0,
        average_recovery_time_seconds: summary.average_recovery_time_seconds ?? 0,
        screen_attention_ratio: summary.screen_attention_ratio ?? 0,
        face_present_ratio: summary.face_present_ratio ?? 0,
        away_event_count: summary.away_event_count ?? 0,
        top_relevant_domains: [],
        top_distraction_domains: [],
        timeline_highlights: [],
        system_observations: [
            `Raw telemetry contains ${summary.interval_count || 0} intervals across ${(summary.top_domains || []).length} domains.`,
            `Total captured duration was ${totalDurationMinutes} minutes.`,
            "Processed focus metrics are not wired yet; teammates' analytics pipeline will populate these fields.",
        ],
        coaching_report:
            "StudyClaw coaching is not connected yet. This page is currently showing raw-backend-backed session metadata with placeholder coaching content until the analytics and OpenClaw layers are integrated.",
    };
}

export const SessionAPI = {
    async createSession({ course, assignment, planned_duration_minutes, user_id = "ryan" }) {
        const data = await request("/sessions", {
            method: "POST",
            body: JSON.stringify({ user_id, course, assignment, planned_duration_minutes }),
        });
        return normalizeSession(data.session);
    },

    async stopSession(sessionId) {
        const data = await request(`/sessions/${sessionId}/stop`, {
            method: "POST",
            body: JSON.stringify({}),
        });
        return normalizeSession(data.session);
    },

    async listSessions() {
        const data = await request("/sessions");
        return (data.sessions || []).map(normalizeSession);
    },

    async getSession(sessionId) {
        const data = await request(`/sessions/${sessionId}`);
        return normalizeSession(data.session);
    },

    async getSessionSummary(sessionId) {
        const [sessionData, summaryData] = await Promise.all([
            request(`/sessions/${sessionId}`),
            request(`/sessions/${sessionId}/summary`),
        ]);
        return buildSummaryFallback(sessionData.session, summaryData.summary || {});
    },

    async getSessionIntervals(sessionId) {
        return request(`/sessions/${sessionId}/intervals`);
    },

    async getStudyClawContext(sessionId) {
        const data = await request(`/sessions/${sessionId}/studyclaw-context`);
        return data.context;
    },
};

export const SystemAPI = {
    async getDebugState() {
        return request("/debug/state");
    },

    async getActiveSession() {
        return request("/sessions/active");
    },
};

export const CanvasAPI = {
    async listCourses(userId = "ryan") {
        const data = await request(`/integrations/canvas/courses?user_id=${encodeURIComponent(userId)}`);
        return data.courses || [];
    },
};

export const ChatAPI = {
    async sendMessage({ message, session_context = "latest", user_id = "ryan" }) {
        const data = await request("/chat/studyclaw", {
            method: "POST",
            body: JSON.stringify({
                message,
                session_context,
                user_id,
            }),
        });
        return data.response;
    },
};
