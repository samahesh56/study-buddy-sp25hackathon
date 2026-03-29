import { cn } from "@/lib/utils";

export default function DomainList({ title, domains, variant = "relevant" }) {
    const barColor = variant === "relevant" ? "bg-primary" : "bg-destructive/70";

    return (
        <div className="bg-card border border-border rounded-xl p-5">
            <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-4">{title}</h3>
            <div className="space-y-3">
                {domains.map((d, i) => (
                    <div key={i}>
                        <div className="flex items-center justify-between mb-1">
                            <span className="text-sm font-medium text-foreground">{d.domain}</span>
                            <span className="text-xs text-muted-foreground">{d.minutes}m · {Math.round(d.percentage * 100)}%</span>
                        </div>
                        <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                            <div
                                className={cn("h-full rounded-full transition-all", barColor)}
                                style={{ width: `${d.percentage * 100 * 2.5}%` }}
                            />
                        </div>
                    </div>
                ))}
                {domains.length === 0 && (
                    <p className="text-xs text-muted-foreground">No domain data available</p>
                )}
            </div>
        </div>
    );
}