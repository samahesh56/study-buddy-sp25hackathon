import { BarChart3, ImageIcon } from "lucide-react";

export default function SessionGraphPanel({ imageUrl }) {
    return (
        <div className="bg-card border border-border rounded-xl overflow-hidden">
            <div className="flex items-center gap-2.5 px-5 py-4 border-b border-border bg-primary/[0.02]">
                <div className="w-8 h-8 rounded-lg bg-accent/10 flex items-center justify-center">
                    <BarChart3 className="w-4.5 h-4.5 text-accent" />
                </div>
                <div>
                    <h3 className="text-sm font-medium text-foreground">Session Graphs</h3>
                    <p className="text-[10px] text-muted-foreground">Primary visualization area for the session PNG export</p>
                </div>
            </div>

            <div className="p-5">
                {imageUrl ? (
                    <img
                        src={imageUrl}
                        alt="Session analytics graphs"
                        className="w-full h-auto rounded-lg border border-border bg-muted/20 object-contain"
                    />
                ) : (
                    <div className="w-full min-h-[320px] md:min-h-[380px] rounded-xl border border-dashed border-border bg-muted/30 flex flex-col items-center justify-center text-center px-6">
                        <div className="w-12 h-12 rounded-2xl bg-card border border-border flex items-center justify-center mb-4">
                            <ImageIcon className="w-5 h-5 text-muted-foreground" />
                        </div>
                        <h4 className="text-sm font-medium text-foreground mb-1">PNG graph slot ready</h4>
                        <p className="max-w-xl text-sm text-muted-foreground leading-relaxed">
                            Drop the generated session PNG here once the analytics pipeline produces it. This area is sized
                            to span the same content width as the top metrics.
                        </p>
                    </div>
                )}
            </div>
        </div>
    );
}
