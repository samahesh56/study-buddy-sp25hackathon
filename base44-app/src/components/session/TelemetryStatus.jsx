import { useEffect, useState } from "react";
import { Wifi, Activity, Clock, Server } from "lucide-react";
import { cn } from "@/lib/utils";
import { SystemAPI } from "@/lib/api";

export default function TelemetryStatus() {
    const [state, setState] = useState(null);

    useEffect(() => {
        let mounted = true;

        const load = async () => {
            try {
                const data = await SystemAPI.getDebugState();
                if (mounted) {
                    setState(data);
                }
            } catch (error) {
                if (mounted) {
                    setState({ error: error.message });
                }
            }
        };

        load();
        const interval = setInterval(load, 10000);

        return () => {
            mounted = false;
            clearInterval(interval);
        };
    }, []);

    const lastTelemetry = state?.recent_intervals?.[0]?.server_received_at ?? "—";

    return (
        <div className="bg-card border border-border rounded-xl p-4">
            <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-widest mb-3">
                System Status
            </div>
            <div className="grid grid-cols-2 gap-3">
                <StatusItem
                    icon={Wifi}
                    label="Extension"
                    value={state?.error ? "Unavailable" : "Unknown"}
                    status={state?.error ? "error" : "idle"}
                />
                <StatusItem
                    icon={Activity}
                    label="Intervals"
                    value={state?.interval_count != null ? String(state.interval_count) : "—"}
                    status={state?.interval_count != null ? "ok" : "waiting"}
                />
                <StatusItem
                    icon={Clock}
                    label="Last Telemetry"
                    value={lastTelemetry}
                    status={lastTelemetry !== "—" ? "ok" : "waiting"}
                />
                <StatusItem
                    icon={Server}
                    label="Processing"
                    value={state?.error ? "Error" : "Raw only"}
                    status={state?.error ? "error" : "idle"}
                />
            </div>
        </div>
    );
}

function StatusItem({ icon: Icon, label, value, status }) {
    const dotColor = {
        ok: "bg-emerald-500",
        waiting: "bg-amber-400",
        idle: "bg-muted-foreground/30",
        error: "bg-red-500",
    }[status] || "bg-muted-foreground/30";

    return (
        <div className="flex items-start gap-2.5">
            <Icon className="w-3.5 h-3.5 text-muted-foreground/50 mt-0.5 shrink-0" />
            <div className="min-w-0">
                <div className="text-[10px] text-muted-foreground uppercase tracking-wider">{label}</div>
                <div className="flex items-center gap-1.5 mt-0.5">
                    <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", dotColor)} />
                    <span className="text-xs font-medium text-foreground truncate">{value}</span>
                </div>
            </div>
        </div>
    );
}
