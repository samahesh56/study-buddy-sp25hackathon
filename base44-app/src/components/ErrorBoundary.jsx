import React from "react";

export default class ErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = { error: null };
    }

    static getDerivedStateFromError(error) {
        return { error };
    }

    componentDidCatch(error, errorInfo) {
        console.error("StudyClaw frontend error:", error, errorInfo);
    }

    render() {
        if (this.state.error) {
            return (
                <div className="min-h-screen flex items-center justify-center bg-slate-50 p-6">
                    <div className="max-w-2xl w-full bg-white border border-slate-200 rounded-xl p-6 space-y-4">
                        <h1 className="text-xl font-semibold text-slate-900">StudyClaw frontend error</h1>
                        <p className="text-sm text-slate-600">
                            The app hit a runtime error while rendering. This screen is shown instead of a blank page so the issue is visible.
                        </p>
                        <pre className="text-xs bg-slate-100 p-4 rounded-lg overflow-auto whitespace-pre-wrap">
                            {String(this.state.error?.stack || this.state.error?.message || this.state.error)}
                        </pre>
                    </div>
                </div>
            );
        }

        return this.props.children;
    }
}
