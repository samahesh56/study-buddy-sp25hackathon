import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Square, BookOpen, FileText, Clock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SessionAPI, SystemAPI } from "@/lib/api";
import { cleanCourseTitle } from "@/lib/course-title";
import { callExtension } from "@/lib/extension-bridge";
import TelemetryStatus from "@/components/session/TelemetryStatus";

export default function ActiveSession() {
    const navigate = useNavigate();
    const [session, setSession] = useState(null);
    const [elapsed, setElapsed] = useState(0);
    const [stopping, setStopping] = useState(false);
    const handlingRemoteStopRef = useRef(false);

    useEffect(() => {
        const stored = sessionStorage.getItem("studyclaw_active_session");
        if (stored) {
            setSession(JSON.parse(stored));
        }
    }, []);

    useEffect(() => {
        if (!session) return;
        const start = new Date(session.started_at).getTime();
        const interval = setInterval(() => {
            setElapsed(Math.floor((Date.now() - start) / 1000));
        }, 1000);
        return () => clearInterval(interval);
    }, [session]);

    useEffect(() => {
        if (!session) return;

        let cancelled = false;

        const checkSessionState = async () => {
            if (handlingRemoteStopRef.current || cancelled) return;

            try {
                const data = await SystemAPI.getActiveSession();
                const activeSession = data?.active_session ?? null;
                if (!activeSession || activeSession.session_id !== session.session_id) {
                    handlingRemoteStopRef.current = true;
                    try {
                        await callExtension("app:stop-session-control", { sessionId: session.session_id });
                    } catch (error) {
                        console.error("Failed to notify extension after backend-initiated stop", error);
                    }
                    sessionStorage.removeItem("studyclaw_active_session");
                    if (!cancelled) {
                        navigate(`/history/${session.session_id}`);
                    }
                }
            } catch (error) {
                console.error("Failed to poll active session state", error);
            }
        };

        const interval = setInterval(checkSessionState, 3000);
        checkSessionState();

        return () => {
            cancelled = true;
            clearInterval(interval);
        };
    }, [navigate, session]);

    const handleStop = async () => {
        if (!session) return;
        setStopping(true);
        handlingRemoteStopRef.current = true;
        try {
            await callExtension("app:stop-session-control", { sessionId: session.session_id });
        } catch (error) {
            console.error("Failed to notify extension to stop capture", error);
        }
        await SessionAPI.stopSession(session.session_id);
        sessionStorage.removeItem("studyclaw_active_session");
        navigate(`/history/${session.session_id}`);
    };

    if (!session) {
        return (
            <div className="px-6 md:px-10 py-8 max-w-2xl mx-auto text-center">
                <div className="py-20">
                    <Clock className="w-12 h-12 text-muted-foreground/30 mx-auto mb-4" />
                    <h2 className="text-lg font-medium text-foreground mb-2">No Active Session</h2>
                    <p className="text-sm text-muted-foreground mb-6">Start a new session to see it here.</p>
                    <Button onClick={() => navigate("/session/start")} className="gap-2">
                        Start Session
                    </Button>
                </div>
            </div>
        );
    }

    const plannedSeconds = session.planned_duration_minutes * 60;
    const remaining = Math.max(0, plannedSeconds - elapsed);
    const progress = Math.min(100, (elapsed / plannedSeconds) * 100);
    const isOvertime = elapsed > plannedSeconds;

    const formatTime = (totalSeconds) => {
        const h = Math.floor(totalSeconds / 3600);
        const m = Math.floor((totalSeconds % 3600) / 60);
        const s = totalSeconds % 60;
        if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
        return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
    };

    return (
        <div className="px-6 md:px-10 py-8 max-w-2xl mx-auto">
            {/* Session Active Indicator */}
            <div className="flex items-center gap-2 mb-8">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse-soft" />
                <span className="text-sm font-medium text-emerald-600">Session Active</span>
            </div>

            {/* Timer Display */}
            <div className="text-center mb-10">
                <div className="text-6xl md:text-7xl font-light text-foreground tracking-tight font-mono mb-2">
                    {formatTime(elapsed)}
                </div>
                <div className="text-sm text-muted-foreground">
                    {isOvertime ? (
                        <span className="text-amber-600">Overtime — planned duration reached</span>
                    ) : (
                        <>{formatTime(remaining)} remaining</>
                    )}
                </div>

                {/* Progress Bar */}
                <div className="mt-6 mx-auto max-w-sm">
                    <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                        <div
                            className="h-full rounded-full transition-all duration-1000 ease-linear"
                            style={{
                                width: `${Math.min(100, progress)}%`,
                                background: isOvertime
                                    ? "hsl(38, 92%, 50%)"
                                    : "hsl(222, 47%, 18%)",
                            }}
                        />
                    </div>
                </div>
            </div>

            {/* Session Info */}
            <div className="bg-card border border-border rounded-xl p-5 mb-6">
                <div className="space-y-3">
                    <div className="flex items-center gap-3">
                        <BookOpen className="w-4 h-4 text-muted-foreground/50 shrink-0" />
                        <div>
                            <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Course</div>
                            <div className="text-sm font-medium text-foreground">{cleanCourseTitle(session.course)}</div>
                        </div>
                    </div>
                    <div className="flex items-center gap-3">
                        <FileText className="w-4 h-4 text-muted-foreground/50 shrink-0" />
                        <div>
                            <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Assignment</div>
                            <div className="text-sm font-medium text-foreground">{session.assignment}</div>
                        </div>
                    </div>
                    <div className="flex items-center gap-3">
                        <Clock className="w-4 h-4 text-muted-foreground/50 shrink-0" />
                        <div>
                            <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Planned Duration</div>
                            <div className="text-sm font-medium text-foreground">{session.planned_duration_minutes} minutes</div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Telemetry Status */}
            <div className="mb-8">
                <TelemetryStatus />
            </div>

            {/* Stop Button */}
            <Button
                onClick={handleStop}
                disabled={stopping}
                variant="destructive"
                className="w-full h-14 text-base font-semibold rounded-xl gap-2"
            >
                {stopping ? (
                    <div className="w-5 h-5 border-2 border-destructive-foreground/30 border-t-destructive-foreground rounded-full animate-spin" />
                ) : (
                    <Square className="w-5 h-5" />
                )}
                {stopping ? "Ending Session..." : "End Session"}
            </Button>

            <p className="text-xs text-center text-muted-foreground mt-3">
                Session ID: <span className="font-mono text-muted-foreground/70">{session.session_id}</span>
            </p>
        </div>
    );
}
