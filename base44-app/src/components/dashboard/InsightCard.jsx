import { Zap } from "lucide-react";

export default function InsightCard() {
    return (
        <div className="bg-card border border-border rounded-xl p-5 relative overflow-hidden">
            <div className="absolute top-0 right-0 w-32 h-32 bg-accent/5 rounded-full -translate-y-1/2 translate-x-1/2" />
            <div className="relative">
                <div className="flex items-center gap-2 mb-3">
                    <div className="w-6 h-6 rounded-md bg-accent/10 flex items-center justify-center">
                        <Zap className="w-3.5 h-3.5 text-accent" />
                    </div>
                    <span className="text-xs font-medium text-accent uppercase tracking-wider">StudyClaw Insight</span>
                </div>
                <p className="text-sm text-foreground leading-relaxed">
                    Your distraction recovery time has dropped from 62s to 45s this week. You're getting better at
                    catching yourself and returning to focused work. Keep it up — consistency here compounds fast.
                </p>
                <p className="text-xs text-muted-foreground mt-3">
                    Based on your last 5 sessions
                </p>
            </div>
        </div>
    );
}