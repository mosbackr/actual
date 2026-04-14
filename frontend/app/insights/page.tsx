"use client";

import { useSession } from "next-auth/react";
import { useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import type {
  AnalystConversationSummary,
  AnalystMessageData,
  AnalystChartConfig,
  AnalystCitation,
} from "@/lib/types";
import { AnalystSidebar } from "@/components/analyst/AnalystSidebar";
import { AnalystChat } from "@/components/analyst/AnalystChat";
import { AnalystInput } from "@/components/analyst/AnalystInput";

export default function InsightsPage() {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;
  const router = useRouter();
  const searchParams = useSearchParams();

  const [conversations, setConversations] = useState<AnalystConversationSummary[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<AnalystMessageData[]>([]);
  const [streamingContent, setStreamingContent] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [loading, setLoading] = useState(true);

  // Let backend 402 responses handle subscription gating rather than
  // relying on a client-side session field that isn't wired through NextAuth.

  // Load conversations list
  const loadConversations = useCallback(async () => {
    if (!token) return;
    try {
      const data = await api.listConversations(token);
      setConversations(data.items);
    } catch {
      // silent
    }
  }, [token]);

  // Load a specific conversation
  const loadConversation = useCallback(
    async (id: string) => {
      if (!token) return;
      try {
        const data = await api.getConversation(token, id);
        setMessages(data.messages);
        setActiveConvId(id);
      } catch {
        // silent
      }
    },
    [token]
  );

  // Initial load
  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }
    loadConversations().then(() => setLoading(false));
  }, [token, loadConversations]);

  // Load conversation from URL param
  useEffect(() => {
    const convId = searchParams.get("c");
    if (convId && token) {
      loadConversation(convId);
    }
  }, [searchParams, token, loadConversation]);

  // Create new conversation
  const handleNew = async () => {
    if (!token) return;
    try {
      const data = await api.createConversation(token);
      setActiveConvId(data.id);
      setMessages([]);
      await loadConversations();
      setSidebarOpen(false);
    } catch (err: any) {
      if (err?.status === 402) {
        alert(err.message || "Subscribe for unlimited analyst access.");
      }
    }
  };

  // Select existing conversation
  const handleSelect = (id: string) => {
    loadConversation(id);
    setSidebarOpen(false);
  };

  // Handle suggestion click
  const handleSuggestion = async (prompt: string) => {
    // Create new conversation and send the suggestion
    if (!token) return;
    try {
      const data = await api.createConversation(token);
      setActiveConvId(data.id);
      setMessages([]);
      await loadConversations();
      setSidebarOpen(false);
      // Send the suggestion as first message after a tick
      setTimeout(() => sendMessage(prompt, data.id), 100);
    } catch (err: any) {
      if (err?.status === 402) {
        alert(err.message || "Subscribe for unlimited analyst access.");
      }
    }
  };

  // Send message and handle SSE stream
  const sendMessage = async (content: string, overrideConvId?: string) => {
    const convId = overrideConvId || activeConvId;
    if (!token || !convId || isStreaming) return;

    // Create conversation if none active
    let targetConvId = convId;
    if (!targetConvId) {
      try {
        const data = await api.createConversation(token);
        targetConvId = data.id;
        setActiveConvId(data.id);
        await loadConversations();
      } catch (err: any) {
        if (err?.status === 402) {
          alert(err.message || "Subscribe for unlimited analyst access.");
        }
        return;
      }
    }

    // Add user message optimistically
    const userMsg: AnalystMessageData = {
      id: `temp-${Date.now()}`,
      role: "user",
      content,
      charts: null,
      citations: null,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setIsStreaming(true);
    setStreamingContent("");

    try {
      const response = await api.streamMessage(token, targetConvId, content);
      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: "Request failed" }));
        throw new Error(err.detail || `Error ${response.status}`);
      }

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let fullText = "";
      let charts: AnalystChartConfig[] = [];
      let citations: AnalystCitation[] = [];
      let currentEvent = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            const dataStr = line.slice(6);
            try {
              const data = JSON.parse(dataStr);

              if (currentEvent === "text") {
                fullText += data.chunk;
                setStreamingContent(fullText);
              } else if (currentEvent === "charts") {
                charts = data.charts || [];
              } else if (currentEvent === "citations") {
                citations = data.citations || [];
              } else if (currentEvent === "error") {
                throw new Error(data.message);
              }
            } catch (parseErr) {
              if (currentEvent === "error") throw parseErr;
            }
          }
        }
      }

      // Add completed assistant message
      const assistantMsg: AnalystMessageData = {
        id: `msg-${Date.now()}`,
        role: "assistant",
        content: fullText,
        charts: charts.length > 0 ? charts : null,
        citations: citations.length > 0 ? citations : null,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
      setStreamingContent("");
      await loadConversations();
    } catch (err: any) {
      // Show error as assistant message
      const errMsg: AnalystMessageData = {
        id: `err-${Date.now()}`,
        role: "assistant",
        content: `Error: ${err.message || "Something went wrong. Please try again."}`,
        charts: null,
        citations: null,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errMsg]);
      setStreamingContent("");
    } finally {
      setIsStreaming(false);
    }
  };

  // Generate report
  const handleGenerateReport = async (format: "docx" | "xlsx") => {
    if (!token || !activeConvId) return;

    try {
      const result = await api.createReport(token, activeConvId, format);

      // Poll for completion
      const poll = async () => {
        const status = await api.getReportStatus(token, result.id);
        if (status.status === "complete") {
          // Trigger download
          const url = api.getReportDownloadUrl(result.id);
          const a = document.createElement("a");
          a.href = url;
          a.download = "";
          // Add auth header via fetch + blob
          const resp = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
          const blob = await resp.blob();
          const blobUrl = URL.createObjectURL(blob);
          a.href = blobUrl;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          URL.revokeObjectURL(blobUrl);
        } else if (status.status === "failed") {
          alert(`Report generation failed: ${status.error || "Unknown error"}`);
        } else {
          setTimeout(poll, 2000);
        }
      };
      setTimeout(poll, 2000);
      alert("Generating report... It will download automatically when ready.");
    } catch (err: any) {
      const msg = err.message || "Failed to generate report.";
      // Backend returns 402 for non-subscribers
      if (msg.includes("402")) {
        alert("Subscribe for $19.99/mo to generate reports.");
      } else {
        alert(msg);
      }
    }
  };

  // Auth gate
  if (!session) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-center">
          <p className="text-xl font-serif text-text-primary mb-2">AI Venture Analyst</p>
          <p className="text-sm text-text-tertiary mb-4">Sign in to access the analyst.</p>
        </div>
      </div>
    );
  }

  if (loading) {
    return <div className="text-center py-20 text-text-tertiary">Loading...</div>;
  }

  return (
    <div className="flex h-[calc(100vh-4rem)]">
      <AnalystSidebar
        conversations={conversations}
        activeId={activeConvId}
        onSelect={handleSelect}
        onNew={handleNew}
        onSuggestion={handleSuggestion}
        isOpen={sidebarOpen}
        onToggle={() => setSidebarOpen(!sidebarOpen)}
      />

      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        {activeConvId && (
          <div className="flex items-center justify-between px-4 py-2 border-b border-border bg-surface">
            <p className="text-sm font-medium text-text-primary truncate">
              {conversations.find((c) => c.id === activeConvId)?.title || "New Conversation"}
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={async () => {
                  if (!token || !activeConvId) return;
                  const result = await api.shareConversation(token, activeConvId);
                  const fullUrl = `${window.location.origin}${result.url}`;
                  navigator.clipboard.writeText(fullUrl);
                  alert("Share link copied to clipboard!");
                }}
                className="text-xs text-text-tertiary hover:text-text-secondary"
              >
                Share
              </button>
              <button
                onClick={async () => {
                  if (!token || !activeConvId) return;
                  if (confirm("Delete this conversation?")) {
                    await api.deleteConversation(token, activeConvId);
                    setActiveConvId(null);
                    setMessages([]);
                    await loadConversations();
                  }
                }}
                className="text-xs text-red-500 hover:text-red-700"
              >
                Delete
              </button>
            </div>
          </div>
        )}

        {/* Chat area */}
        <AnalystChat
          messages={messages}
          streamingContent={streamingContent}
          isStreaming={isStreaming}
        />

        {/* Input */}
        <AnalystInput
          onSend={(msg) => sendMessage(msg)}
          onGenerateReport={handleGenerateReport}
          isStreaming={isStreaming}
          hasMessages={messages.length > 0}
          isSubscriber={true}
        />
      </div>
    </div>
  );
}
