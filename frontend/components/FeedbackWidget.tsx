"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useSession } from "next-auth/react";
import { usePathname } from "next/navigation";
import { api } from "@/lib/api";

interface Message {
  role: "user" | "assistant";
  content: string;
}

const OPENING_MESSAGE: Message = {
  role: "assistant",
  content:
    "What's on your mind? I'm here to collect feedback about DeepThesis — bugs, feature requests, or anything that could be better.",
};

export function FeedbackWidget() {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;
  const pathname = usePathname();

  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([OPENING_MESSAGE]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [completed, setCompleted] = useState(false);
  const [messageCount, setMessageCount] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = useCallback(async () => {
    if (!token || !input.trim() || streaming) return;

    const userMessage = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: userMessage }]);
    setStreaming(true);

    try {
      // Create session on first message
      let sid = sessionId;
      if (!sid) {
        const { id } = await api.createFeedbackSession(token, pathname);
        sid = id;
        setSessionId(id);
      }

      // Send message and stream response
      const response = await api.sendFeedbackMessage(token, sid, userMessage);
      if (!response.ok) {
        throw new Error("Failed to send message");
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error("No response stream");

      const decoder = new TextDecoder();
      let assistantText = "";
      setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        let currentEvent = "";
        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            const data = line.slice(6);
            try {
              const parsed = JSON.parse(data);
              if (currentEvent === "text" && parsed.chunk) {
                assistantText += parsed.chunk;
                setMessages((prev) => {
                  const updated = [...prev];
                  updated[updated.length - 1] = {
                    role: "assistant",
                    content: assistantText,
                  };
                  return updated;
                });
              } else if (currentEvent === "error" && parsed.message) {
                setMessages((prev) => {
                  const updated = [...prev];
                  updated[updated.length - 1] = {
                    role: "assistant",
                    content: "Sorry, something went wrong. Please try again.",
                  };
                  return updated;
                });
              }
            } catch {
              // skip unparseable
            }
            currentEvent = "";
          }
        }
      }

      const newCount = messageCount + 1;
      setMessageCount(newCount);

      // Auto-complete after 4+ user messages (agent has had enough context)
      if (newCount >= 4) {
        try {
          await api.completeFeedbackSession(token, sid);
          setCompleted(true);
        } catch {
          // non-critical
        }
      }
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Sorry, something went wrong. Please try again." },
      ]);
    } finally {
      setStreaming(false);
    }
  }, [token, input, streaming, sessionId, pathname, messageCount]);

  const handleClose = useCallback(async () => {
    // Abandon if not completed and has a session
    if (sessionId && !completed) {
      try {
        if (messageCount >= 2) {
          await api.completeFeedbackSession(token!, sessionId);
        } else {
          await api.abandonFeedbackSession(token!, sessionId);
        }
      } catch {
        // non-critical
      }
    }
    setOpen(false);
    // Reset state for next time
    setMessages([OPENING_MESSAGE]);
    setInput("");
    setSessionId(null);
    setCompleted(false);
    setMessageCount(0);
  }, [sessionId, completed, token, messageCount]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  if (!session) return null;

  return (
    <>
      {/* Floating bubble */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          className="fixed bottom-6 right-6 z-50 flex h-12 w-12 items-center justify-center rounded-full bg-accent text-white shadow-lg hover:bg-accent/90 transition"
          aria-label="Share feedback"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
        </button>
      )}

      {/* Expanded panel */}
      {open && (
        <div className="fixed bottom-6 right-6 z-50 flex w-[380px] flex-col rounded-xl border border-border bg-surface shadow-2xl"
          style={{ height: "500px" }}
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <h3 className="text-sm font-medium text-text-primary">Share Feedback</h3>
            <button
              onClick={handleClose}
              className="text-text-tertiary hover:text-text-primary transition"
              aria-label="Close feedback"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>

          {/* Messages */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                    msg.role === "user"
                      ? "bg-accent text-white"
                      : "bg-surface-alt text-text-primary"
                  }`}
                >
                  {msg.content || (
                    <span className="inline-block animate-pulse text-text-tertiary">...</span>
                  )}
                </div>
              </div>
            ))}
            {completed && (
              <div className="text-center text-xs text-text-tertiary py-2">
                Feedback submitted. Thank you!
              </div>
            )}
          </div>

          {/* Input */}
          {!completed && (
            <div className="border-t border-border px-3 py-3">
              <div className="flex items-end gap-2">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Type your feedback..."
                  rows={1}
                  disabled={streaming}
                  className="flex-1 resize-none rounded-lg border border-border bg-background px-3 py-2 text-sm text-text-primary placeholder:text-text-tertiary focus:border-accent focus:outline-none disabled:opacity-50"
                />
                <button
                  onClick={handleSend}
                  disabled={!input.trim() || streaming}
                  className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent text-white hover:bg-accent/90 transition disabled:opacity-40 disabled:cursor-not-allowed"
                  aria-label="Send"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="22" y1="2" x2="11" y2="13" />
                    <polygon points="22 2 15 22 11 13 2 9 22 2" />
                  </svg>
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </>
  );
}
