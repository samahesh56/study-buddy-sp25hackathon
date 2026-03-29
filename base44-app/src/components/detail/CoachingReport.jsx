import { Zap } from "lucide-react";
import ReactMarkdown from "react-markdown";

export default function CoachingReport({ report, observations }) {
    return (
        <div className="bg-card border border-border rounded-xl overflow-hidden">
            {/* Header */}
            <div className="flex items-center gap-2.5 px-5 py-4 border-b border-border bg-primary/[0.02]">
                <div className="w-7 h-7 rounded-lg bg-accent/10 flex items-center justify-center">
                    <Zap className="w-4 h-4 text-accent" />
                </div>
                <div>
                    <h3 className="text-sm font-medium text-foreground">StudyClaw Coaching Report</h3>
                    <p className="text-[10px] text-muted-foreground">Personalized analysis for this session</p>
                </div>
            </div>

            {/* Report */}
            <div className="p-5">
                <div className="prose prose-sm prose-slate max-w-none text-sm leading-relaxed text-foreground/90">
                    <ReactMarkdown>{report}</ReactMarkdown>
                </div>
            </div>

            {/* Observations */}
            {observations && observations.length > 0 && (
                <div className="px-5 pb-5">
                    <div className="border-t border-border pt-4">
                        <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-3">Key Observations</h4>
                        <ul className="space-y-2">
                            {observations.map((obs, i) => (
                                <li key={i} className="flex gap-2.5 text-sm text-foreground/80">
                                    <span className="w-1 h-1 rounded-full bg-accent mt-2 shrink-0" />
                                    <span>{obs}</span>
                                </li>
                            ))}
                        </ul>
                    </div>
                </div>
            )}
        </div>
    );
}