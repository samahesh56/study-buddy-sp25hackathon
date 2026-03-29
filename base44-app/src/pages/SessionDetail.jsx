import { useState, useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import { ArrowLeft, Clock, Calendar } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SessionAPI } from "@/lib/api";
import MetricGrid from "@/components/detail/MetricGrid";
import DomainList from "@/components/detail/DomainList";
import Timeline from "@/components/detail/Timeline";
import CoachingReport from "@/components/detail/CoachingReport";
import moment from "moment";

export default function SessionDetail() {
    const navigate = useNavigate();
    const urlParams = new URLSearchParams(window.location.search);
    const pathParts = window.location.pathname.split("/");
    const sessionId = pathParts[pathParts.length - 1];

    const [session, setSession] = useState(null);
    const [summary, setSummary] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        Promise.all([
            SessionAPI.getSession(sessionId),
            SessionAPI.getSessionSummary(sessionId),
        ]).then(([sess, sum]) => {
            setSession(sess);
            setSummary(sum);
            setLoading(false);
        });
    }, [sessionId]);

    if (loading) {
        return (
            <div className="flex items-center justify-center h-full py-20">
                <div className="w-6 h-6 border-2 border-muted border-t-foreground rounded-full animate-spin" />
            </div>
        );
    }

    if (!session || !summary) {
        return (
            <div className="px-6 md:px-10 py-8 text-center">
                <p className="text-muted-foreground">Session not found.</p>
                <Button onClick={() => navigate("/history")} variant="outline" className="mt-4">Back to History</Button>
            </div>
        );
    }

    const focusColor = summary.focus_score >= 80 ? "text-emerald-600" :
        summary.focus_score >= 60 ? "text-amber-600" : "text-red-500";

    return (
        <div className="px-6 md:px-10 py-8 max-w-5xl mx-auto">
            {/* Header */}
            <div className="mb-8">
                <button
                    onClick={() => navigate("/history")}
                    className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors mb-4"
                >
                    <ArrowLeft className="w-4 h-4" /> Back to History
                </button>

                <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
                    <div>
                        <h1 className="text-2xl font-semibold text-foreground tracking-tight mb-1">
                            {session.course}
                        </h1>
                        <p className="text-sm text-muted-foreground">{session.assignment}</p>
                    </div>
                    <div className="flex items-center gap-4">
                        <div className="text-right">
                            <div className={`text-3xl font-bold ${focusColor}`}>{summary.focus_score}</div>
                            <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Focus Score</div>
                        </div>
                    </div>
                </div>

                {/* Session Meta */}
                <div className="flex flex-wrap items-center gap-4 mt-4 text-xs text-muted-foreground">
                    <span className="flex items-center gap-1.5">
                        <Calendar className="w-3.5 h-3.5" />
                        {moment(session.started_at).format("MMMM D, YYYY · h:mm A")}
                    </span>
                    <span className="flex items-center gap-1.5">
                        <Clock className="w-3.5 h-3.5" />
                        {summary.actual_duration_minutes}m of {summary.planned_duration_minutes}m planned
                    </span>
                    <span className="font-mono text-muted-foreground/50">{session.session_id}</span>
                </div>
            </div>

            {/* Metrics */}
            <div className="mb-8">
                <h2 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-3">Session Metrics</h2>
                <MetricGrid summary={summary} />
            </div>

            {/* Attention */}
            <div className="grid md:grid-cols-3 gap-3 mb-8">
                <AttentionCard label="Screen Attention" value={`${Math.round(summary.screen_attention_ratio * 100)}%`} />
                <AttentionCard label="Face Present" value={`${Math.round(summary.face_present_ratio * 100)}%`} />
                <AttentionCard label="Relevant → Irrelevant" value={`${summary.relevant_to_irrelevant_switch_count} switches`} />
            </div>

            {/* Domains */}
            <div className="grid md:grid-cols-2 gap-4 mb-8">
                <DomainList title="Top Relevant Domains" domains={summary.top_relevant_domains} variant="relevant" />
                <DomainList title="Top Distraction Domains" domains={summary.top_distraction_domains} variant="distraction" />
            </div>

            {/* Timeline */}
            <div className="mb-8">
                <Timeline highlights={summary.timeline_highlights} />
            </div>

            {/* Coaching Report */}
            <div className="mb-8">
                <CoachingReport report={summary.coaching_report} observations={summary.system_observations} />
            </div>

            {/* CTA */}
            <div className="text-center py-6">
                <Link to={`/chat`}>
                    <Button variant="outline" className="gap-2">
                        Discuss this session with StudyClaw →
                    </Button>
                </Link>
            </div>
        </div>
    );
}

function AttentionCard({ label, value }) {
    return (
        <div className="bg-card border border-border rounded-xl p-4">
            <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider mb-1">{label}</div>
            <div className="text-lg font-semibold text-foreground">{value}</div>
        </div>
    );
}
