const cardConfig = [
    {
        key: "focus",
        label: "Focus %",
        getValue: (summary) => `${Math.round(summary.focus_score ?? 0)}%`,
        helper: "Overall session focus"
    },
    {
        key: "distractions",
        label: "Distractions",
        getValue: (summary) => `${summary.distraction_event_count ?? 0}`,
        helper: "Detected distraction events"
    },
    {
        key: "top-site",
        label: "Top Site Visited",
        getValue: (summary) => summary.top_domains?.[0]?.domain ?? "None",
        helper: "Most visited domain this session"
    },
    {
        key: "tab-switches",
        label: "Tab Switches",
        getValue: (summary) => `${summary.tab_switch_count ?? 0}`,
        helper: "Browser tab changes detected"
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
