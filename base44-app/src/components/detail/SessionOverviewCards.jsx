const cardConfig = [
    {
        key: "focus",
        label: "Focus %",
        getValue: (summary) => `${Math.round(summary.focus_score ?? 0)}%`,
        helper: "Overall session focus"
    },
    {
        key: "on-task",
        label: "On Task %",
        getValue: (summary) => `${Math.round((summary.on_task_ratio ?? 0) * 100)}%`,
        helper: "Relevant work time"
    },
    {
        key: "off-task",
        label: "Off Task %",
        getValue: (summary) => `${Math.round((summary.off_task_ratio ?? 0) * 100)}%`,
        helper: "Distracting time"
    },
    {
        key: "distractions",
        label: "Distractions",
        getValue: (summary) => `${summary.distraction_event_count ?? 0}`,
        helper: "Detected distraction events"
    }
];

export default function SessionOverviewCards({ summary }) {
    return (
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
            {cardConfig.map((card) => (
                <div key={card.key} className="bg-card border border-border rounded-xl p-4">
                    <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider mb-1.5">
                        {card.label}
                    </div>
                    <div className="text-2xl font-semibold tracking-tight text-foreground">
                        {card.getValue(summary)}
                    </div>
                    <div className="text-xs text-muted-foreground mt-1">
                        {card.helper}
                    </div>
                </div>
            ))}
        </div>
    );
}
