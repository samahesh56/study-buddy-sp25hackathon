import { useState } from "react";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";

const PRESETS = [5, 25, 45, 60];

export default function DurationPicker({ value, onChange }) {
    const [isCustom, setIsCustom] = useState(!PRESETS.includes(value));

    const handlePreset = (minutes) => {
        setIsCustom(false);
        onChange(minutes);
    };

    const handleCustom = () => {
        setIsCustom(true);
        if (!value || PRESETS.includes(value)) {
            onChange(30);
        }
    };

    return (
        <div>
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-3 block">
                Session Duration
            </label>
            <div className="grid grid-cols-5 gap-2">
                {PRESETS.map(m => (
                    <button
                        key={m}
                        type="button"
                        onClick={() => handlePreset(m)}
                        className={cn(
                            "relative flex flex-col items-center justify-center py-4 rounded-xl border-2 transition-all duration-150 cursor-pointer",
                            !isCustom && value === m
                                ? "border-primary bg-primary/5 shadow-sm"
                                : "border-border hover:border-primary/30 bg-card"
                        )}
                    >
                        <span className={cn(
                            "text-xl font-semibold",
                            !isCustom && value === m ? "text-primary" : "text-foreground"
                        )}>
                            {m}
                        </span>
                        <span className="text-[10px] text-muted-foreground uppercase tracking-wider mt-0.5">min</span>
                    </button>
                ))}
                <button
                    type="button"
                    onClick={handleCustom}
                    className={cn(
                        "relative flex flex-col items-center justify-center py-4 rounded-xl border-2 transition-all duration-150 cursor-pointer",
                        isCustom
                            ? "border-primary bg-primary/5 shadow-sm"
                            : "border-border hover:border-primary/30 bg-card"
                    )}
                >
                    <span className={cn(
                        "text-sm font-medium",
                        isCustom ? "text-primary" : "text-muted-foreground"
                    )}>
                        Custom
                    </span>
                </button>
            </div>

            {isCustom && (
                <div className="mt-3 flex items-center gap-2">
                    <Input
                        type="number"
                        min={5}
                        max={240}
                        value={value}
                        onChange={e => onChange(parseInt(e.target.value) || 5)}
                        className="w-24 text-center text-lg font-semibold"
                        autoFocus
                    />
                    <span className="text-sm text-muted-foreground">minutes</span>
                </div>
            )}
        </div>
    );
}
