import { cn } from "@/lib/utils";

export default function MetricGrid({ summary }) {
    const metrics = [
        { label: "Focus Score", value: summary.focus_score, unit: "/100", highlight: true },
        { label: "On-Task", value: `${Math.round(summary.on_task_ratio * 100)}%`, sublabel: `${summary.active_on_task_minutes + summary.passive_on_task_minutes}m total` },
        { label: "Off-Task", value: `${Math.round(summary.off_task_ratio * 100)}%`, sublabel: `${summary.off_task_minutes}m total` },
        { label: "Idle", value: `${summary.idle_minutes}m`, sublabel: `${Math.round(summary.unknown_ratio * 100)}% unknown` },
        { label: "Planned", value: `${summary.planned_duration_minutes}m` },
        { label: "Actual", value: `${summary.actual_duration_minutes}m` },
        { label: "Longest Streak", value: `${summary.longest_focus_streak_minutes}m` },
        { label: "Avg Streak", value: `${summary.average_focus_streak_minutes}m` },
        { label: "Tab Switches", value: summary.tab_switch_count },
        { label: "Distractions", value: summary.distraction_event_count },
        { label: "Avg Recovery", value: `${summary.average_recovery_time_seconds}s` },
        { label: "Away Events", value: summary.away_event_count },
    ];

    return (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {metrics.map(m => (
                <div
                    key={m.label}
                    className={cn(
                        "bg-card border border-border rounded-xl p-4",
                        m.highlight && "md:col-span-1 border-primary/20 bg-primary/[0.02]"
                    )}
                >
                    <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider mb-1">{m.label}</div>
                    <div className={cn(
                        "text-xl font-semibold tracking-tight",
                        m.highlight ? "text-primary" : "text-foreground"
                    )}>
                        {m.value}{m.unit && <span className="text-sm font-normal text-muted-foreground">{m.unit}</span>}
                    </div>
                    {m.sublabel && <div className="text-[10px] text-muted-foreground mt-0.5">{m.sublabel}</div>}
                </div>
            ))}
        </div>
    );
}