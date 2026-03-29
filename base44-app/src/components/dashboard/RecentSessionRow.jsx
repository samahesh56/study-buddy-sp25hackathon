import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import moment from "moment";
import { cleanCourseTitle } from "@/lib/course-title";

export default function RecentSessionRow({ session }) {
    const focusColor = session.focus_score >= 80 ? "text-emerald-600" :
        session.focus_score >= 60 ? "text-amber-600" : "text-red-500";

    return (
        <Link
            to={`/history/${session.session_id}`}
            className="flex items-center gap-4 px-4 py-3.5 rounded-lg hover:bg-muted/50 transition-colors group"
        >
            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-foreground truncate">{cleanCourseTitle(session.course)}</span>
                    <span className="text-xs text-muted-foreground">·</span>
                    <span className="text-xs text-muted-foreground truncate">{session.assignment}</span>
                </div>
                <div className="text-xs text-muted-foreground mt-0.5">
                    {moment(session.started_at).fromNow()} · {session.actual_duration_minutes || session.planned_duration_minutes} min
                </div>
            </div>
            <div className="flex items-center gap-3 shrink-0">
                <div className="text-right">
                    <div className={`text-sm font-semibold ${focusColor}`}>{session.focus_score}</div>
                    <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Focus</div>
                </div>
                <ChevronRight className="w-4 h-4 text-muted-foreground/40 group-hover:text-muted-foreground transition-colors" />
            </div>
        </Link>
    );
}
