import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Play, BookOpen, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SessionAPI } from "@/lib/api";
import DurationPicker from "@/components/session/DurationPicker";

export default function StartSession() {
    const navigate = useNavigate();
    const [course, setCourse] = useState("");
    const [assignment, setAssignment] = useState("");
    const [duration, setDuration] = useState(45);
    const [starting, setStarting] = useState(false);

    const canStart = course.trim() && assignment.trim() && duration >= 5;

    const handleStart = async () => {
        if (!canStart) return;
        setStarting(true);

        const session = await SessionAPI.createSession({
            course: course.trim(),
            assignment: assignment.trim(),
            planned_duration_minutes: duration,
        });

        // Store active session in sessionStorage for the active session page
        sessionStorage.setItem("studyclaw_active_session", JSON.stringify({
            ...session,
            started_at: new Date().toISOString(),
        }));

        navigate("/session/active");
    };

    return (
        <div className="px-6 md:px-10 py-8 max-w-2xl mx-auto">
            <div className="mb-8">
                <h1 className="text-2xl font-semibold text-foreground tracking-tight mb-1">Start a Session</h1>
                <p className="text-sm text-muted-foreground">Set up your study session. StudyClaw will collect and analyze your focus in the background.</p>
            </div>

            <div className="space-y-8">
                {/* Course */}
                <div>
                    <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2 block">
                        Course
                    </label>
                    <div className="relative">
                        <BookOpen className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground/50" />
                        <Input
                            placeholder="e.g. CMPSC 132"
                            value={course}
                            onChange={e => setCourse(e.target.value)}
                            className="pl-10 h-12 text-base rounded-xl border-border"
                        />
                    </div>
                </div>

                {/* Assignment */}
                <div>
                    <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2 block">
                        Assignment
                    </label>
                    <div className="relative">
                        <FileText className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground/50" />
                        <Input
                            placeholder="e.g. Linked List Homework"
                            value={assignment}
                            onChange={e => setAssignment(e.target.value)}
                            className="pl-10 h-12 text-base rounded-xl border-border"
                        />
                    </div>
                </div>

                {/* Duration */}
                <DurationPicker value={duration} onChange={setDuration} />

                {/* Summary & Start */}
                <div className="pt-4 border-t border-border">
                    {canStart && (
                        <div className="bg-muted/50 rounded-xl p-4 mb-6">
                            <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">Session Setup</div>
                            <div className="space-y-1.5">
                                <div className="flex justify-between text-sm">
                                    <span className="text-muted-foreground">Course</span>
                                    <span className="font-medium text-foreground">{course}</span>
                                </div>
                                <div className="flex justify-between text-sm">
                                    <span className="text-muted-foreground">Assignment</span>
                                    <span className="font-medium text-foreground">{assignment}</span>
                                </div>
                                <div className="flex justify-between text-sm">
                                    <span className="text-muted-foreground">Duration</span>
                                    <span className="font-medium text-foreground">{duration} minutes</span>
                                </div>
                            </div>
                        </div>
                    )}

                    <Button
                        onClick={handleStart}
                        disabled={!canStart || starting}
                        className="w-full h-14 text-base font-semibold rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 gap-2 shadow-lg"
                    >
                        {starting ? (
                            <div className="w-5 h-5 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin" />
                        ) : (
                            <Play className="w-5 h-5" />
                        )}
                        {starting ? "Starting..." : "Start Session"}
                    </Button>
                </div>
            </div>
        </div>
    );
}