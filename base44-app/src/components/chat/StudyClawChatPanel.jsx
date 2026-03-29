import { useEffect, useRef, useState } from "react";
import { Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ChatAPI, SessionAPI } from "@/lib/api";
import { cleanCourseTitle } from "@/lib/course-title";
import ChatBubble from "@/components/chat/ChatBubble";
import justClawLogo from "@/assets/just-claw.png";

const INITIAL_MESSAGE = {
    role: "assistant",
    content:
        "Hey! I'm StudyClaw, your study coach. I track patterns across your sessions and help you build better focus habits. Ask me anything about your study performance, or I can break down your latest session.",
    timestamp: new Date().toISOString(),
};

const SUGGESTIONS = [
    "How has my focus been this week?",
    "What are my biggest distractions?",
    "How can I improve my longest focus streak?",
];

export default function StudyClawChatPanel({
    initialContext = "latest",
    fixedContext = false,
    title = "StudyClaw",
    subtitle = "Your personal study coach",
    className = ""
}) {
    const [messages, setMessages] = useState([INITIAL_MESSAGE]);
    const [input, setInput] = useState("");
    const [sending, setSending] = useState(false);
    const [sessionContext, setSessionContext] = useState(initialContext);
    const [sessions, setSessions] = useState([]);
    const scrollRef = useRef(null);

    useEffect(() => {
        setSessionContext(initialContext);
    }, [initialContext]);

    useEffect(() => {
        SessionAPI.listSessions().then(setSessions);
    }, []);

    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [messages]);

    const handleSend = async (text) => {
        const msg = (text || input).trim();
        if (!msg || sending) return;

        const userMessage = {
            role: "user",
            content: msg,
            timestamp: new Date().toISOString(),
        };

        setMessages((prev) => [...prev, userMessage]);
        setInput("");
        setSending(true);

        const response = await ChatAPI.sendMessage({
            message: msg,
            session_context: sessionContext === "none" ? null : sessionContext,
        });

        setMessages((prev) => [...prev, response]);
        setSending(false);
    };

    const handleKeyDown = (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    return (
        <div className={`flex flex-col bg-card border border-border rounded-xl overflow-hidden ${className}`.trim()}>
            <div className="flex items-center justify-between px-6 py-4 border-b border-border bg-primary/[0.02]">
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-primary/10 ring-1 ring-border flex items-center justify-center overflow-hidden">
                        <img src={justClawLogo} alt="StudyClaw" className="w-8 h-8 object-contain" />
                    </div>
                    <div>
                        <h2 className="text-sm font-semibold text-foreground">{title}</h2>
                        <p className="text-[10px] text-muted-foreground">{subtitle}</p>
                    </div>
                </div>

                {!fixedContext && (
                    <Select value={sessionContext} onValueChange={setSessionContext}>
                        <SelectTrigger className="w-48 h-8 text-xs">
                            <SelectValue placeholder="Session context" />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="latest">Latest Session</SelectItem>
                            {sessions.map((session) => (
                                <SelectItem key={session.session_id} value={session.session_id}>
                                    {cleanCourseTitle(session.course) || "Session"} {session.assignment ? `- ${session.assignment}` : ""}
                                </SelectItem>
                            ))}
                            <SelectItem value="none">No session context</SelectItem>
                        </SelectContent>
                    </Select>
                )}
            </div>

            <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-6 space-y-5 min-h-[320px] max-h-[560px]">
                {messages.map((msg, index) => (
                    <ChatBubble key={index} message={msg} />
                ))}

                {sending && (
                    <div className="flex gap-3">
                        <div className="w-8 h-8 rounded-lg bg-primary/10 ring-1 ring-border flex items-center justify-center shrink-0 overflow-hidden">
                            <img src={justClawLogo} alt="StudyClaw" className="w-6 h-6 object-contain" />
                        </div>
                        <div className="bg-card border border-border rounded-2xl rounded-bl-md px-4 py-3">
                            <div className="flex gap-1.5">
                                <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/40 animate-bounce" style={{ animationDelay: "0ms" }} />
                                <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/40 animate-bounce" style={{ animationDelay: "150ms" }} />
                                <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/40 animate-bounce" style={{ animationDelay: "300ms" }} />
                            </div>
                        </div>
                    </div>
                )}

                {messages.length <= 1 && !sending && (
                    <div className="flex flex-wrap gap-2 pt-2">
                        {SUGGESTIONS.map((suggestion) => (
                            <button
                                key={suggestion}
                                onClick={() => handleSend(suggestion)}
                                className="text-xs px-3.5 py-2 rounded-full border border-border bg-card text-foreground hover:border-primary/30 hover:bg-muted/50 transition-colors"
                            >
                                {suggestion}
                            </button>
                        ))}
                    </div>
                )}
            </div>

            <div className="px-6 py-4 border-t border-border bg-card">
                <div className="flex items-center gap-2 max-w-3xl mx-auto">
                    <Input
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="Ask StudyClaw about this session..."
                        className="flex-1 h-11 rounded-xl text-sm"
                        disabled={sending}
                    />
                    <Button
                        onClick={() => handleSend()}
                        disabled={!input.trim() || sending}
                        size="icon"
                        className="h-11 w-11 rounded-xl shrink-0"
                    >
                        <Send className="w-4 h-4" />
                    </Button>
                </div>
            </div>
        </div>
    );
}
