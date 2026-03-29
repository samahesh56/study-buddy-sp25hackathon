import { cn } from "@/lib/utils";

export default function MetricCard({ label, value, sublabel, icon: Icon, trend, className }) {
    return (
        <div className={cn("bg-card border border-border rounded-xl p-5", className)}>
            <div className="flex items-start justify-between mb-3">
                <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{label}</span>
                {Icon && <Icon className="w-4 h-4 text-muted-foreground/60" />}
            </div>
            <div className="text-2xl font-semibold text-foreground tracking-tight">{value}</div>
            {(sublabel || trend) && (
                <div className="flex items-center gap-2 mt-1.5">
                    {trend && (
                        <span className={cn(
                            "text-xs font-medium",
                            trend > 0 ? "text-emerald-600" : trend < 0 ? "text-red-500" : "text-muted-foreground"
                        )}>
                            {trend > 0 ? "+" : ""}{trend}%
                        </span>
                    )}
                    {sublabel && <span className="text-xs text-muted-foreground">{sublabel}</span>}
                </div>
            )}
        </div>
    );
}