import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { CanvasAPI, SessionAPI } from "@/lib/api";
import { callExtension } from "@/lib/extension-bridge";
import DurationPicker from "@/components/session/DurationPicker";

export default function StartSession() {
    const navigate = useNavigate();
    const [course, setCourse] = useState("");
    const [duration, setDuration] = useState(45);
    const [starting, setStarting] = useState(false);
    const [courses, setCourses] = useState([]);
    const [loadingCourses, setLoadingCourses] = useState(true);
    const [importingCourses, setImportingCourses] = useState(false);

    const loadCourses = async () => {
        setLoadingCourses(true);
        try {
            const importedCourses = await CanvasAPI.listCourses("ryan");
            setCourses(importedCourses);
        } catch (error) {
            console.error("Failed to load Canvas courses", error);
            setCourses([]);
        } finally {
            setLoadingCourses(false);
        }
    };

    useEffect(() => {
        loadCourses();
    }, []);

    const canStart = course.trim() && duration >= 5;

    const handleStart = async () => {
        if (!canStart) return;
        setStarting(true);

        const session = await SessionAPI.createSession({
            course: course.trim(),
            assignment: null,
            planned_duration_minutes: duration,
        });

        try {
            await callExtension("app:start-session-control", { session });
        } catch (error) {
            console.error("Failed to notify extension to start capture", error);
        }

        // Store active session in sessionStorage for the active session page
        sessionStorage.setItem("studyclaw_active_session", JSON.stringify({
            ...session,
            started_at: new Date().toISOString(),
        }));

        navigate("/session/active");
    };

    const handleImportCourses = async () => {
        setImportingCourses(true);
        try {
            await callExtension("app:import-canvas-courses", { userId: "ryan" }, 15000);
            await loadCourses();
        } catch (error) {
            console.error("Failed to import Canvas courses from extension", error);
            alert(error.message);
        } finally {
            setImportingCourses(false);
        }
    };

    return (
        <div className="px-6 md:px-10 py-8 max-w-2xl mx-auto">
            <div className="mb-8">
                <h1 className="text-2xl font-semibold text-foreground tracking-tight mb-1">Start a Session</h1>
                <p className="text-sm text-muted-foreground">Choose a Canvas course, set your study time, and start the session.</p>
            </div>

            <div className="space-y-8">
                {/* Course */}
                <div>
                    <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2 block">
                        Course
                    </label>

                    {!loadingCourses && courses.length > 0 ? (
                        <Select
                            value={course}
                            onValueChange={setCourse}
                        >
                            <SelectTrigger className="h-12 rounded-xl">
                                <SelectValue placeholder="Select a Canvas course" />
                            </SelectTrigger>
                            <SelectContent>
                                {courses.map((item) => (
                                    <SelectItem key={`${item.canvas_instance_domain}-${item.external_course_id}`} value={item.name}>
                                        {item.name}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    ) : (
                        <div className="h-12 rounded-xl border border-border bg-muted/40 flex items-center px-4 text-sm text-muted-foreground">
                            {loadingCourses
                                ? "Loading imported Canvas courses..."
                                : "No imported Canvas courses found. Import your courses from the extension first."}
                        </div>
                    )}

                    {!loadingCourses && courses.length === 0 && (
                        <p className="text-xs text-muted-foreground mt-2">
                            Import your Canvas courses to populate this dropdown.
                        </p>
                    )}

                    {courses.length > 0 && (
                        <p className="text-xs text-muted-foreground mt-2">
                            Loaded {courses.length} cached Canvas course{courses.length === 1 ? "" : "s"} from the backend.
                        </p>
                    )}

                    {!loadingCourses && courses.length === 0 && (
                        <Button
                            type="button"
                            variant="outline"
                            onClick={handleImportCourses}
                            disabled={importingCourses}
                            className="mt-3"
                        >
                            {importingCourses ? "Importing..." : "Import Canvas Courses"}
                        </Button>
                    )}
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
