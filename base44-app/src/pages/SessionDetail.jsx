import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Calendar, Clock } from "lucide-react";
import moment from "moment";
import { Button } from "@/components/ui/button";
import { SessionAPI } from "@/lib/api";
import SessionOverviewCards from "@/components/detail/SessionOverviewCards";
import SessionGraphPanel from "@/components/detail/SessionGraphPanel";
import StudyClawChatPanel from "@/components/chat/StudyClawChatPanel";

export default function SessionDetail() {
    const navigate = useNavigate();
    const pathParts = window.location.pathname.split("/");
    const sessionId = pathParts[pathParts.length - 1];

    const [session, setSession] = useState(null);
    const [summary, setSummary] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        Promise.all([
            SessionAPI.getSession(sessionId),
            SessionAPI.getSessionSummary(sessionId),
        ]).then(([sessionData, summaryData]) => {
            setSession(sessionData);
            setSummary(summaryData);
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
                <Button onClick={() => navigate("/history")} variant="outline" className="mt-4">
                    Back to History
                </Button>
            </div>
        );
    }

    const graphImageUrl = summary.graph_image_url || summary.graph_png_url || summary.graph_image_src || null;

    return (
        <div className="px-6 md:px-10 py-8 max-w-6xl mx-auto">
            <div className="mb-8">
                <button
                    onClick={() => navigate("/history")}
                    className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors mb-4"
                >
                    <ArrowLeft className="w-4 h-4" /> Back to History
                </button>

                <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
                    <div>
                        <h1 className="text-2xl font-semibold text-foreground tracking-tight mb-1">
                            {session.course || "Study Session"}
                        </h1>
                        <p className="text-sm text-muted-foreground">
                            Post-session review and coaching workspace
                        </p>
                    </div>

                    <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
                        <span className="flex items-center gap-1.5">
                            <Calendar className="w-3.5 h-3.5" />
                            {moment(session.started_at).format("MMMM D, YYYY · h:mm A")}
                        </span>
                        <span className="flex items-center gap-1.5">
                            <Clock className="w-3.5 h-3.5" />
                            {summary.actual_duration_minutes}m of {summary.planned_duration_minutes}m planned
                        </span>
                    </div>
                </div>
            </div>

            <div className="space-y-8">
                <section>
                    <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-3">
                        Session Overview
                    </div>
                    <SessionOverviewCards summary={summary} />
                </section>

                <section>
                    <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-3">
                        Analytics Graph
                    </div>
                    <SessionGraphPanel imageUrl={graphImageUrl} />
                </section>

                <section>
                    <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-3">
                        OpenClaw Chat
                    </div>
                    <StudyClawChatPanel
                        initialContext={session.session_id}
                        fixedContext
                        title="OpenClaw Session Chat"
                        subtitle="Discuss this completed session with your study coach"
                    />
                </section>
            </div>
        </div>
    );
}
