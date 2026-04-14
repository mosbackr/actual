"use client";

import { useEffect, useRef } from "react";
import { AnalystMessage } from "./AnalystMessage";
import type { AnalystMessageData } from "@/lib/types";

interface Props {
  messages: AnalystMessageData[];
  streamingContent: string;
  isStreaming: boolean;
}

export function AnalystChat({ messages, streamingContent, isStreaming }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, streamingContent]);

  if (messages.length === 0 && !isStreaming) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center max-w-md">
          <p className="text-2xl font-serif text-text-primary mb-2">AI Venture Analyst</p>
          <p className="text-sm text-text-tertiary mb-6">
            Ask me anything about your portfolio, market trends, competitor analysis, or due diligence.
            I have access to your startup database and external market intelligence.
          </p>
          <div className="grid grid-cols-2 gap-2 text-xs">
            {[
              "What's our strongest sector?",
              "Compare top 5 by AI score",
              "Fintech funding trends",
              "Which startups need attention?",
            ].map((q) => (
              <div
                key={q}
                className="px-3 py-2 rounded border border-border text-text-tertiary bg-surface"
              >
                {q}
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
      {messages.map((msg) => (
        <AnalystMessage
          key={msg.id}
          role={msg.role}
          content={msg.content}
          charts={msg.charts}
          citations={msg.citations}
        />
      ))}

      {/* Streaming assistant message */}
      {isStreaming && streamingContent && (
        <AnalystMessage
          role="assistant"
          content={streamingContent}
          isStreaming={true}
        />
      )}

      {/* Typing indicator when streaming hasn't produced text yet */}
      {isStreaming && !streamingContent && (
        <div className="flex gap-3">
          <div className="w-7 h-7 rounded-full bg-accent/10 text-accent flex items-center justify-center text-xs font-medium">
            DT
          </div>
          <div className="bg-surface border border-border rounded-lg px-4 py-3">
            <div className="flex gap-1">
              <span className="w-2 h-2 bg-text-tertiary rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
              <span className="w-2 h-2 bg-text-tertiary rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
              <span className="w-2 h-2 bg-text-tertiary rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
            </div>
          </div>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
}
