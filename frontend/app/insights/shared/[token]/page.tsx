"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AnalystMessage } from "@/components/analyst/AnalystMessage";
import type { AnalystSharedConversation } from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

export default function SharedConversationPage() {
  const params = useParams();
  const shareToken = params.token as string;

  const [conversation, setConversation] = useState<AnalystSharedConversation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!shareToken) return;
    fetch(`${API_BASE}/api/analyst/shared/${shareToken}`)
      .then(async (res) => {
        if (!res.ok) throw new Error("Conversation not found");
        return res.json();
      })
      .then(setConversation)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [shareToken]);

  if (loading) {
    return <div className="text-center py-20 text-text-tertiary">Loading...</div>;
  }

  if (error || !conversation) {
    return (
      <div className="text-center py-20">
        <p className="text-text-primary text-lg mb-2">Not Found</p>
        <p className="text-text-tertiary text-sm">{error || "This shared conversation doesn't exist."}</p>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto py-8 px-4">
      <div className="mb-6">
        <p className="text-xs text-text-tertiary uppercase tracking-wider mb-1">Shared Conversation</p>
        <h1 className="font-serif text-2xl text-text-primary">{conversation.title}</h1>
        <p className="text-xs text-text-tertiary mt-1">
          {conversation.message_count} messages
        </p>
      </div>

      <div className="space-y-4">
        {conversation.messages.map((msg) => (
          <AnalystMessage
            key={msg.id}
            role={msg.role}
            content={msg.content}
            charts={msg.charts}
            citations={msg.citations}
          />
        ))}
      </div>

      <div className="mt-8 text-center">
        <p className="text-xs text-text-tertiary">
          Powered by Deep Thesis AI Analyst
        </p>
      </div>
    </div>
  );
}
