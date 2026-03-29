import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { Play, Target, Clock, Flame, MessageCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SessionAPI } from "@/lib/api";
import { cleanCourseTitle } from "@/lib/course-title";
import studyClawLogo from "@/assets/studyclaw-logo.png";
import MetricCard from "@/components/dashboard/MetricCard";
import RecentSessionRow from "@/components/dashboard/RecentSessionRow";
import InsightCard from "@/components/dashboard/InsightCard";
import TrendChart from "@/components/dashboard/TrendChart";

export default function Dashboard() {
    const [sessions, setSessions] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        SessionAPI.listSessions().then(data => {
            setSessions(data);
            setLoading(false);
        });
    }, []);

    const recentSessions = sessions.slice(0, 4);
    const avgFocus = sessions.length > 0
        ? Math.round(sessions.reduce((a, s) => a + (s.focus_score || 0), 0) / sessions.length)
        : 0;
    const totalMinutes = sessions.reduce((a, s) => a + (s.actual_duration_minutes || 0), 0);
    const bestStreak = Math.max(...sessions.map(s => s.focus_score || 0), 0);
    const topCourse = cleanCourseTitle(sessions[0]?.course) || "None yet";

    if (loading) {
        return (
            <div className="flex items-center justify-center h-full">
                <div className="w-6 h-6 border-2 border-muted border-t-foreground rounded-full animate-spin" />
            </div>
        );
    }

    return (
        <div className="px-6 md:px-10 py-8 max-w-6xl mx-auto">
            {/* Hero / Start Session */}
            <div className="mb-8">
                <div className="bg-primary rounded-2xl p-8 md:p-10 relative overflow-hidden">
                    <div className="absolute inset-0 bg-gradient-to-br from-transparent via-transparent to-black/10" />
                    <div className="relative flex flex-col md:flex-row md:items-center md:justify-between gap-6">
                        <div>
                            <img
                                src={studyClawLogo}
                                alt="StudyClaw"
                                className="h-16 md:h-20 w-auto object-contain mb-4 drop-shadow-[0_10px_24px_rgba(0,0,0,0.18)]"
                            />
                            <h1 className="text-2xl md:text-3xl font-semibold text-primary-foreground tracking-tight mb-2">
                                Ready to study?
                            </h1>
                            <p className="text-primary-foreground/70 text-sm md:text-base max-w-md">
                                Start a focused session and let StudyClaw track your progress in the background.
                            </p>
                        </div>
                        <Link to="/session/start">
                            <Button size="lg" className="bg-accent text-accent-foreground hover:bg-accent/90 shadow-lg gap-2 text-base px-8 py-6 rounded-xl font-semibold">
                                <Play className="w-5 h-5" />
                                Start Session
                            </Button>
                        </Link>
                    </div>
                </div>
            </div>

            {/* Metrics Row */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
                <MetricCard label="Avg Focus" value={avgFocus} sublabel="this week" icon={Target} trend={5} />
                <MetricCard label="Sessions" value={sessions.length} sublabel="this week" icon={Flame} />
                <MetricCard label="Total Time" value={`${totalMinutes}m`} sublabel="studied" icon={Clock} />
                <MetricCard label="Best Score" value={bestStreak} sublabel="this week" icon={Target} trend={3} />
            </div>

            {/* Main Content Grid */}
            <div className="grid md:grid-cols-5 gap-6">
                {/* Left: Recent Sessions + Trend */}
                <div className="md:col-span-3 space-y-6">
                    <div className="bg-card border border-border rounded-xl">
                        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
                            <h2 className="text-sm font-medium text-foreground">Recent Sessions</h2>
                            <Link to="/history" className="text-xs text-muted-foreground hover:text-foreground transition-colors">
                                View all →
                            </Link>
                        </div>
                        <div className="divide-y divide-border/50">
                            {recentSessions.map(session => (
                                <RecentSessionRow key={session.session_id} session={session} />
                            ))}
                        </div>
                    </div>

                    <TrendChart />
                </div>

                {/* Right: Insight + Chat CTA */}
                <div className="md:col-span-2 space-y-6">
                    <InsightCard />

                    <Link to="/chat" className="block">
                        <div className="bg-card border border-border rounded-xl p-5 hover:border-accent/30 transition-colors group">
                            <div className="flex items-center gap-3 mb-3">
                                <div className="w-9 h-9 rounded-xl bg-primary flex items-center justify-center">
                                    <MessageCircle className="w-4.5 h-4.5 text-primary-foreground" />
                                </div>
                                <div>
                                    <h3 className="text-sm font-medium text-foreground">Talk to StudyClaw</h3>
                                    <p className="text-xs text-muted-foreground">Ask about your habits and progress</p>
                                </div>
                            </div>
                            <p className="text-xs text-muted-foreground leading-relaxed">
                                "How has my focus been this week?" "What can I do to reduce distractions?"
                            </p>
                        </div>
                    </Link>

                    <div className="bg-card border border-border rounded-xl p-5">
                        <h3 className="text-sm font-medium text-foreground mb-3">Quick Stats</h3>
                        <div className="space-y-3">
                            <div className="flex items-center justify-between">
                                <span className="text-xs text-muted-foreground">Avg. Recovery Time</span>
                                <span className="text-sm font-medium text-foreground">45s</span>
                            </div>
                            <div className="flex items-center justify-between">
                                <span className="text-xs text-muted-foreground">Best Focus Streak</span>
                                <span className="text-sm font-medium text-foreground">14 min</span>
                            </div>
                            <div className="flex items-center justify-between">
                                <span className="text-xs text-muted-foreground">Top Course</span>
                                <span className="text-sm font-medium text-foreground">{topCourse}</span>
                            </div>
                            <div className="flex items-center justify-between">
                                <span className="text-xs text-muted-foreground">Distractions / Session</span>
                                <span className="text-sm font-medium text-foreground">~4</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
