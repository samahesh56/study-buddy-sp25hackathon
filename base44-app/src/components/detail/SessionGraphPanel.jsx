import { useEffect, useState } from "react";
import { BarChart3, Camera, ChevronLeft, ChevronRight, ImageIcon } from "lucide-react";

export default function SessionGraphPanel({ imageUrl, distractionImages = [] }) {
    const [selectedIndex, setSelectedIndex] = useState(0);

    useEffect(() => {
        setSelectedIndex(0);
    }, [distractionImages.length]);

    const selectedImage = distractionImages[selectedIndex] || null;

    return (
        <div className="space-y-6">
            <div className="bg-card border border-border rounded-xl overflow-hidden">
                <div className="flex items-center gap-2.5 px-5 py-4 border-b border-border bg-primary/[0.02]">
                    <div className="w-8 h-8 rounded-lg bg-accent/10 flex items-center justify-center">
                        <BarChart3 className="w-4.5 h-4.5 text-accent" />
                    </div>
                    <div>
                        <h3 className="text-sm font-medium text-foreground">Session Graphs</h3>
                        <p className="text-[10px] text-muted-foreground">Computer-vision summary export for this session</p>
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
                            <h4 className="text-sm font-medium text-foreground mb-1">Graph not available</h4>
                            <p className="max-w-xl text-sm text-muted-foreground leading-relaxed">
                                This session does not have a completed PNG export yet. Once the computer-vision summary is saved,
                                it will render here automatically.
                            </p>
                        </div>
                    )}
                </div>
            </div>

            <div className="bg-card border border-border rounded-xl overflow-hidden">
                <div className="flex items-center gap-2.5 px-5 py-4 border-b border-border bg-primary/[0.02]">
                    <div className="w-8 h-8 rounded-lg bg-accent/10 flex items-center justify-center">
                        <Camera className="w-4.5 h-4.5 text-accent" />
                    </div>
                    <div>
                        <h3 className="text-sm font-medium text-foreground">Distraction Snapshots</h3>
                        <p className="text-[10px] text-muted-foreground">Camera captures from distracted or away moments</p>
                    </div>
                </div>

                <div className="p-5 space-y-4">
                    {selectedImage ? (
                        <>
                            <div className="relative rounded-xl border border-border bg-muted/20 overflow-hidden">
                                <img
                                    src={selectedImage.url}
                                    alt={`Distraction snapshot ${selectedIndex + 1}`}
                                    className="w-full h-auto object-contain"
                                />
                                <div className="absolute left-4 right-4 bottom-4 flex items-center justify-between gap-3">
                                    <button
                                        type="button"
                                        onClick={() => setSelectedIndex((current) => Math.max(current - 1, 0))}
                                        disabled={selectedIndex === 0}
                                        className="inline-flex items-center gap-1 rounded-full bg-background/90 px-3 py-1.5 text-xs text-foreground disabled:opacity-40"
                                    >
                                        <ChevronLeft className="w-3.5 h-3.5" />
                                        Previous
                                    </button>
                                    <div className="rounded-full bg-background/90 px-3 py-1.5 text-xs text-muted-foreground">
                                        {selectedIndex + 1} / {distractionImages.length}
                                    </div>
                                    <button
                                        type="button"
                                        onClick={() => setSelectedIndex((current) => Math.min(current + 1, distractionImages.length - 1))}
                                        disabled={selectedIndex === distractionImages.length - 1}
                                        className="inline-flex items-center gap-1 rounded-full bg-background/90 px-3 py-1.5 text-xs text-foreground disabled:opacity-40"
                                    >
                                        Next
                                        <ChevronRight className="w-3.5 h-3.5" />
                                    </button>
                                </div>
                            </div>
                        </>
                    ) : (
                        <div className="w-full min-h-[180px] rounded-xl border border-dashed border-border bg-muted/30 flex flex-col items-center justify-center text-center px-6">
                            <div className="w-12 h-12 rounded-2xl bg-card border border-border flex items-center justify-center mb-4">
                                <Camera className="w-5 h-5 text-muted-foreground" />
                            </div>
                            <h4 className="text-sm font-medium text-foreground mb-1">No distraction snapshots saved</h4>
                            <p className="max-w-xl text-sm text-muted-foreground leading-relaxed">
                                If the camera classifier captures distracted moments for this session, they will show here as a review strip.
                            </p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
