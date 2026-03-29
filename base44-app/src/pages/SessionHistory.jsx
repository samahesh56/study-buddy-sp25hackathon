import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { ChevronRight, Clock, Target } from "lucide-react";
import { SessionAPI } from "@/lib/api";
import moment from "moment";
import { cn } from "@/lib/utils";

export default function SessionHistory() {
    const [sessions, setSessions] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        SessionAPI.listSessions().then(data => {
            setSessions(data);
            setLoading(false);
        });
    }, []);

    if (loading) {
        return (
            <div className="flex items-center justify-center h-full py-20">
                <div className="w-6 h-6 border-2 border-muted border-t-foreground rounded-full animate-spin" />
            </div>
        );
    }

    return (
        <div className="px-6 md:px-10 py-8 max-w-4xl mx-auto">
            <div className="mb-8">
                <h1 className="text-2xl font-semibold text-foreground tracking-tight mb-1">Session History</h1>
                <p className="text-sm text-muted-foreground">{sessions.length} sessions recorded</p>
            </div>

            <div className="space-y-2">
                {sessions.map(session => (
                    <SessionCard key={session.session_id} session={session} />
                ))}
            </div>

            {sessions.length === 0 && (
                <div className="text-center py-20">
                    <Clock className="w-12 h-12 text-muted-foreground/20 mx-auto mb-4" />
                    <p className="text-muted-foreground">No sessions yet. Start your first session!</p>
                </div>
            )}
        </div>
    );
}

function SessionCard({ session }) {
    const focusColor = session.focus_score >= 80 ? "text-emerald-600 bg-emerald-50" :
        session.focus_score >= 60 ? "text-amber-600 bg-amber-50" : "text-red-500 bg-red-50";

    const statusColors = {
        completed: "text-emerald-600 bg-emerald-50",
        active: "text-blue-600 bg-blue-50",
        stopped: "text-muted-foreground bg-muted",
    };

    return (
        <Link
            to={`/history/${session.session_id}`}
            className="flex items-center gap-4 bg-card border border-border rounded-xl px-5 py-4 hover:border-primary/20 hover:shadow-sm transition-all group"
        >
            {/* Focus Score Badge */}
            <div className={cn("w-12 h-12 rounded-xl flex flex-col items-center justify-center shrink-0", focusColor)}>
                <span className="text-lg font-bold leading-none">{session.focus_score || "—"}</span>
                <span className="text-[8px] uppercase tracking-wider font-medium mt-0.5">Focus</span>
            </div>

            {/* Info */}
            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-sm font-medium text-foreground truncate">{session.course}</span>
                    <span className={cn("text-[10px] px-1.5 py-0.5 rounded-full font-medium", statusColors[session.status] || statusColors.completed)}>
                        {session.status}
                    </span>
                </div>
                <div className="text-xs text-muted-foreground truncate">{session.assignment}</div>
                <div className="flex items-center gap-3 mt-1.5 text-xs text-muted-foreground">
                    <span>{moment(session.started_at).format("MMM D, h:mm A")}</span>
                    <span>·</span>
                    <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {session.actual_duration_minutes || session.planned_duration_minutes}m
                    </span>
                    {session.on_task_ratio != null && (
                        <>
                            <span>·</span>
                            <span className="flex items-center gap-1">
                                <Target className="w-3 h-3" />
                                {Math.round(session.on_task_ratio * 100)}% on-task
                            </span>
                        </>
                    )}
                </div>
            </div>

            <ChevronRight className="w-4 h-4 text-muted-foreground/30 group-hover:text-muted-foreground transition-colors shrink-0" />
        </Link>
    );
}