import { useState, useEffect, useRef } from "react";
import { Send, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ChatAPI, SessionAPI } from "@/lib/api";
import ChatBubble from "@/components/chat/ChatBubble";

const INITIAL_MESSAGE = {
    role: "assistant",
    content: "Hey! I'm StudyClaw, your study coach. I track patterns across your sessions and help you build better focus habits. Ask me anything about your study performance, or I can break down your latest session.",
    timestamp: new Date().toISOString(),
};

const SUGGESTIONS = [
    "How has my focus been this week?",
    "What are my biggest distractions?",
    "How can I improve my longest focus streak?",
];

export default function StudyClawChat() {
    const [messages, setMessages] = useState([INITIAL_MESSAGE]);
    const [input, setInput] = useState("");
    const [sending, setSending] = useState(false);
    const [sessionContext, setSessionContext] = useState("latest");
    const [sessions, setSessions] = useState([]);
    const scrollRef = useRef(null);

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

        setMessages(prev => [...prev, userMessage]);
        setInput("");
        setSending(true);

        const response = await ChatAPI.sendMessage({
            message: msg,
            session_context: sessionContext === "none" ? null : sessionContext,
        });

        setMessages(prev => [...prev, response]);
        setSending(false);
    };

    const handleKeyDown = (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    return (
        <div className="flex flex-col h-full">
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-border bg-card">
                <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-xl bg-primary flex items-center justify-center">
                        <Zap className="w-4.5 h-4.5 text-primary-foreground" />
                    </div>
                    <div>
                        <h1 className="text-sm font-semibold text-foreground">StudyClaw</h1>
                        <p className="text-[10px] text-muted-foreground">Your personal study coach</p>
                    </div>
                </div>

                {/* Context Selector */}
                <Select value={sessionContext} onValueChange={setSessionContext}>
                    <SelectTrigger className="w-48 h-8 text-xs">
                        <SelectValue placeholder="Session context" />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="latest">Latest Session</SelectItem>
                        {sessions.map(s => (
                            <SelectItem key={s.session_id} value={s.session_id}>
                                {s.course} — {s.assignment}
                            </SelectItem>
                        ))}
                        <SelectItem value="none">No session context</SelectItem>
                    </SelectContent>
                </Select>
            </div>

            {/* Messages */}
            <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-6 space-y-5">
                {messages.map((msg, i) => (
                    <ChatBubble key={i} message={msg} />
                ))}

                {sending && (
                    <div className="flex gap-3">
                        <div className="w-7 h-7 rounded-lg bg-primary flex items-center justify-center shrink-0">
                            <Zap className="w-3.5 h-3.5 text-primary-foreground" />
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

                {/* Suggestion chips */}
                {messages.length <= 1 && !sending && (
                    <div className="flex flex-wrap gap-2 pt-2">
                        {SUGGESTIONS.map(s => (
                            <button
                                key={s}
                                onClick={() => handleSend(s)}
                                className="text-xs px-3.5 py-2 rounded-full border border-border bg-card text-foreground hover:border-primary/30 hover:bg-muted/50 transition-colors"
                            >
                                {s}
                            </button>
                        ))}
                    </div>
                )}
            </div>

            {/* Input */}
            <div className="px-6 py-4 border-t border-border bg-card">
                <div className="flex items-center gap-2 max-w-3xl mx-auto">
                    <Input
                        value={input}
                        onChange={e => setInput(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="Ask StudyClaw about your study habits..."
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