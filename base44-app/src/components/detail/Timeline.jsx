import { cn } from "@/lib/utils";
import { Zap, AlertTriangle, ArrowRight, Pause, Settings } from "lucide-react";

const typeConfig = {
    system: { icon: Settings, color: "text-muted-foreground", dot: "bg-muted-foreground/40" },
    focus: { icon: Zap, color: "text-emerald-600", dot: "bg-emerald-500" },
    distraction: { icon: AlertTriangle, color: "text-amber-600", dot: "bg-amber-500" },
    recovery: { icon: ArrowRight, color: "text-blue-600", dot: "bg-blue-500" },
    idle: { icon: Pause, color: "text-muted-foreground", dot: "bg-muted-foreground/40" },
};

export default function Timeline({ highlights }) {
    return (
        <div className="bg-card border border-border rounded-xl p-5">
            <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-4">Timeline</h3>
            <div className="space-y-0">
                {highlights.map((h, i) => {
                    const config = typeConfig[h.type] || typeConfig.system;
                    const Icon = config.icon;
                    const isLast = i === highlights.length - 1;

                    return (
                        <div key={i} className="flex gap-3">
                            <div className="flex flex-col items-center">
                                <div className={cn("w-2 h-2 rounded-full mt-1.5 shrink-0", config.dot)} />
                                {!isLast && <div className="w-px flex-1 bg-border my-1" />}
                            </div>
                            <div className="pb-4">
                                <div className="flex items-center gap-2">
                                    <span className="text-xs font-mono text-muted-foreground">{h.time}</span>
                                    <span className={cn("text-sm", config.color)}>{h.event}</span>
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}