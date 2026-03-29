import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

const data = [
    { session: "Mar 22", focus: 65, onTask: 62 },
    { session: "Mar 23", focus: 72, onTask: 70 },
    { session: "Mar 24", focus: 88, onTask: 85 },
    { session: "Mar 25", focus: 92, onTask: 89 },
    { session: "Mar 26", focus: 71, onTask: 68 },
    { session: "Mar 27", focus: 85, onTask: 82 },
    { session: "Mar 28", focus: 78, onTask: 74 },
];

export default function TrendChart() {
    return (
        <div className="bg-card border border-border rounded-xl p-5">
            <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-medium text-foreground">Focus Trend</h3>
                <span className="text-xs text-muted-foreground">Last 7 sessions</span>
            </div>
            <div className="h-48">
                <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={data} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
                        <defs>
                            <linearGradient id="focusGrad" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="hsl(222, 47%, 18%)" stopOpacity={0.15} />
                                <stop offset="95%" stopColor="hsl(222, 47%, 18%)" stopOpacity={0} />
                            </linearGradient>
                            <linearGradient id="taskGrad" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="hsl(38, 92%, 50%)" stopOpacity={0.15} />
                                <stop offset="95%" stopColor="hsl(38, 92%, 50%)" stopOpacity={0} />
                            </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="hsl(220, 13%, 89%)" vertical={false} />
                        <XAxis dataKey="session" tick={{ fontSize: 11 }} stroke="hsl(220, 9%, 46%)" axisLine={false} tickLine={false} />
                        <YAxis tick={{ fontSize: 11 }} stroke="hsl(220, 9%, 46%)" axisLine={false} tickLine={false} domain={[50, 100]} />
                        <Tooltip
                            contentStyle={{
                                background: "hsl(0, 0%, 100%)",
                                border: "1px solid hsl(220, 13%, 89%)",
                                borderRadius: "8px",
                                fontSize: "12px",
                            }}
                        />
                        <Area type="monotone" dataKey="focus" stroke="hsl(222, 47%, 18%)" strokeWidth={2} fill="url(#focusGrad)" name="Focus Score" />
                        <Area type="monotone" dataKey="onTask" stroke="hsl(38, 92%, 50%)" strokeWidth={2} fill="url(#taskGrad)" name="On-Task %" />
                    </AreaChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
}