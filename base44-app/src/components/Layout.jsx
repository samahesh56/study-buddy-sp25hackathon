import { Outlet, Link, useLocation } from "react-router-dom";
import { LayoutDashboard, Play, Clock, History, MessageCircle, Zap } from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
    { path: "/", label: "Dashboard", icon: LayoutDashboard },
    { path: "/session/start", label: "New Session", icon: Play },
    { path: "/session/active", label: "Active Session", icon: Clock },
    { path: "/history", label: "History", icon: History },
    { path: "/chat", label: "StudyClaw", icon: MessageCircle },
];

export default function Layout() {
    const location = useLocation();

    return (
        <div className="flex h-screen overflow-hidden bg-background">
            {/* Sidebar */}
            <aside className="hidden md:flex flex-col w-64 bg-sidebar border-r border-sidebar-border">
                <div className="flex items-center gap-2.5 px-6 py-5 border-b border-sidebar-border">
                    <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-sidebar-primary">
                        <Zap className="w-4 h-4 text-sidebar-primary-foreground" />
                    </div>
                    <span className="text-lg font-semibold text-sidebar-foreground tracking-tight">StudyClaw</span>
                </div>

                <nav className="flex-1 px-3 py-4 space-y-1">
                    {navItems.map(item => {
                        const isActive = location.pathname === item.path ||
                            (item.path !== "/" && location.pathname.startsWith(item.path));
                        const Icon = item.icon;

                        return (
                            <Link
                                key={item.path}
                                to={item.path}
                                className={cn(
                                    "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150",
                                    isActive
                                        ? "bg-sidebar-accent text-sidebar-accent-foreground"
                                        : "text-sidebar-foreground/70 hover:text-sidebar-foreground hover:bg-sidebar-accent/50"
                                )}
                            >
                                <Icon className="w-4.5 h-4.5 shrink-0" />
                                <span>{item.label}</span>
                                {item.label === "StudyClaw" && (
                                    <span className="ml-auto w-2 h-2 rounded-full bg-sidebar-primary animate-pulse-soft" />
                                )}
                            </Link>
                        );
                    })}
                </nav>

                <div className="px-4 py-4 border-t border-sidebar-border">
                    <div className="text-xs text-sidebar-foreground/40">StudyClaw v0.1</div>
                </div>
            </aside>

            {/* Mobile header */}
            <div className="md:hidden fixed top-0 left-0 right-0 z-50 bg-sidebar border-b border-sidebar-border">
                <div className="flex items-center justify-between px-4 py-3">
                    <div className="flex items-center gap-2">
                        <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-sidebar-primary">
                            <Zap className="w-3.5 h-3.5 text-sidebar-primary-foreground" />
                        </div>
                        <span className="text-base font-semibold text-sidebar-foreground">StudyClaw</span>
                    </div>
                </div>
                <nav className="flex px-2 pb-2 gap-1 overflow-x-auto">
                    {navItems.map(item => {
                        const isActive = location.pathname === item.path ||
                            (item.path !== "/" && location.pathname.startsWith(item.path));
                        const Icon = item.icon;

                        return (
                            <Link
                                key={item.path}
                                to={item.path}
                                className={cn(
                                    "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium whitespace-nowrap transition-colors",
                                    isActive
                                        ? "bg-sidebar-accent text-sidebar-accent-foreground"
                                        : "text-sidebar-foreground/60 hover:text-sidebar-foreground"
                                )}
                            >
                                <Icon className="w-3.5 h-3.5" />
                                <span>{item.label}</span>
                            </Link>
                        );
                    })}
                </nav>
            </div>

            {/* Main content */}
            <main className="flex-1 overflow-y-auto md:pt-0 pt-24">
                <div className="min-h-full">
                    <Outlet />
                </div>
            </main>
        </div>
    );
}