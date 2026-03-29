import { cn } from "@/lib/utils";
import justClawLogo from "@/assets/just-claw.png";

export default function ChatBubble({ message }) {
    const isAssistant = message.role === "assistant";

    return (
        <div className={cn("flex gap-3", isAssistant ? "justify-start" : "justify-end")}>
            {isAssistant && (
                <div className="w-8 h-8 rounded-lg bg-primary/10 ring-1 ring-border flex items-center justify-center shrink-0 mt-1 overflow-hidden">
                    <img src={justClawLogo} alt="StudyClaw" className="w-6 h-6 object-contain" />
                </div>
            )}

            <div
                className={cn(
                    "max-w-[80%] rounded-2xl px-4 py-3",
                    isAssistant
                        ? "bg-card border border-border rounded-bl-md"
                        : "bg-primary text-primary-foreground rounded-br-md"
                )}
            >
                <p className="text-sm leading-relaxed whitespace-pre-wrap">{message.content}</p>
                {message.timestamp && (
                    <div
                        className={cn(
                            "mt-2 text-[10px]",
                            isAssistant ? "text-muted-foreground" : "text-primary-foreground/70"
                        )}
                    >
                        {new Date(message.timestamp).toLocaleTimeString([], {
                            hour: "numeric",
                            minute: "2-digit",
                        })}
                    </div>
                )}
            </div>
        </div>
    );
}
