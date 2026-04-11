"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useSession } from "next-auth/react";
import { AccessDenied } from "@/components/AccessDenied";
import { Sidebar } from "@/components/Sidebar";
import { adminApi } from "@/lib/api";
import type { ChatMessage, StartupCandidate } from "@/lib/types";

const STORAGE_KEY = "acutal-scout-chat";

const STAGE_LABELS: Record<string, string> = {
  pre_seed: "Pre-Seed",
  seed: "Seed",
  series_a: "Series A",
  series_b: "Series B",
  series_c: "Series C",
  growth: "Growth",
};

const SUGGESTIONS = [
  "Find YC W25 batch AI startups",
  "Search for climate tech startups that raised seed rounds in 2024",
  "Find fintech startups in New York",
  "What are the most promising AI infrastructure startups right now?",
];

function StartupCard({
  startup,
  selected,
  onToggle,
  index,
}: {
  startup: StartupCandidate;
  selected: boolean;
  onToggle: () => void;
  index: number;
}) {
  const isDup = startup.already_on_platform === true;

  return (
    <div
      onClick={isDup ? undefined : onToggle}
      className={`rounded border p-3 transition ${
        isDup
          ? "opacity-60 cursor-not-allowed border-border bg-surface"
          : selected
            ? "border-accent bg-accent/5 cursor-pointer"
            : "border-border bg-surface hover:border-text-tertiary cursor-pointer"
      }`}
    >
      <div className="flex items-start gap-3">
        <div className="mt-0.5 shrink-0">
          {isDup ? (
            <div className="w-5 h-5 flex items-center justify-center text-xs text-text-tertiary">&mdash;</div>
          ) : (
            <div
              className={`w-5 h-5 rounded border-2 flex items-center justify-center text-xs transition ${
                selected
                  ? "border-accent bg-accent text-white"
                  : "border-border"
              }`}
            >
              {selected && "\u2713"}
            </div>
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs text-text-tertiary">#{index + 1}</span>
            <h4 className="font-medium text-text-primary text-sm truncate">{startup.name}</h4>
            <span className="shrink-0 text-xs px-1.5 py-0.5 rounded border border-border text-text-tertiary">
              {STAGE_LABELS[startup.stage] || startup.stage}
            </span>
            {isDup && (
              <span className="shrink-0 text-xs px-1.5 py-0.5 rounded bg-text-tertiary/10 text-text-tertiary">
                Already {startup.existing_status || "on platform"}
              </span>
            )}
          </div>
          <p className="text-xs text-text-secondary mt-1 line-clamp-2">{startup.description}</p>
          <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2 text-xs text-text-tertiary">
            {startup.website_url && (
              <a
                href={startup.website_url.startsWith("http") ? startup.website_url : `https://${startup.website_url}`}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="hover:text-accent transition"
              >
                {startup.website_url.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "")}
              </a>
            )}
            {startup.location_city && (
              <span>{startup.location_city}{startup.location_state ? `, ${startup.location_state}` : ""}</span>
            )}
            {startup.founders && <span>Founded by {startup.founders}</span>}
            {startup.funding_raised && <span>{startup.funding_raised} raised</span>}
            {startup.key_investors && <span>Investors: {startup.key_investors}</span>}
          </div>
        </div>
      </div>
    </div>
  );
}

function StartupResults({
  startups,
  selected,
  onToggle,
  onSelectAll,
  onAddSelected,
  adding,
}: {
  startups: StartupCandidate[];
  selected: Set<number>;
  onToggle: (i: number) => void;
  onSelectAll: () => void;
  onAddSelected: () => void;
  adding: boolean;
}) {
  return (
    <div className="space-y-2 mt-3">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-xs text-text-tertiary">{startups.length} startups found</span>
        <button
          onClick={onSelectAll}
          className="text-xs text-accent hover:text-accent-hover transition"
        >
          {selected.size === startups.length ? "Deselect all" : "Select all"}
        </button>
        {selected.size > 0 && (
          <button
            onClick={onAddSelected}
            disabled={adding}
            className="ml-auto text-xs px-3 py-1 bg-accent text-white rounded hover:bg-accent-hover disabled:opacity-50 transition"
          >
            {adding ? "Adding..." : `Add ${selected.size} to triage`}
          </button>
        )}
      </div>
      {startups.map((s, i) => (
        <StartupCard
          key={`${s.name}-${i}`}
          startup={s}
          selected={selected.has(i)}
          onToggle={() => onToggle(i)}
          index={i}
        />
      ))}
    </div>
  );
}

export default function ScoutPage() {
  const { data: session, status } = useSession();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [adding, setAdding] = useState(false);
  const [selectedByMessage, setSelectedByMessage] = useState<Record<number, Set<number>>>({});
  const [addedMessages, setAddedMessages] = useState<Set<number>>(new Set());
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const didLoad = useRef(false);

  // Load chat from localStorage on mount
  useEffect(() => {
    if (didLoad.current) return;
    didLoad.current = true;
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const data = JSON.parse(stored);
        if (data.messages?.length) {
          setMessages(data.messages);
        }
        if (data.addedMessages?.length) {
          setAddedMessages(new Set(data.addedMessages));
        }
      }
    } catch {
      // ignore corrupt data
    }
  }, []);

  // Save chat to localStorage whenever messages change
  useEffect(() => {
    if (!didLoad.current) return;
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          messages,
          addedMessages: [...addedMessages],
        }),
      );
    } catch {
      // storage full or unavailable
    }
  }, [messages, addedMessages]);

  if (status === "loading") return null;
  if (!session || session.role !== "superadmin") return <AccessDenied />;

  function scrollToBottom() {
    setTimeout(() => messagesEndRef.current?.scrollIntoView({ behavior: "smooth" }), 100);
  }

  function toggleSelection(msgIndex: number, startupIndex: number) {
    setSelectedByMessage((prev) => {
      const current = new Set(prev[msgIndex] || []);
      if (current.has(startupIndex)) {
        current.delete(startupIndex);
      } else {
        current.add(startupIndex);
      }
      return { ...prev, [msgIndex]: current };
    });
  }

  function toggleSelectAll(msgIndex: number, total: number) {
    setSelectedByMessage((prev) => {
      const current = prev[msgIndex] || new Set();
      if (current.size === total) {
        return { ...prev, [msgIndex]: new Set() };
      }
      return { ...prev, [msgIndex]: new Set(Array.from({ length: total }, (_, i) => i)) };
    });
  }

  async function handleAddSelected(msgIndex: number) {
    const msg = messages[msgIndex];
    if (!msg.startups || !session?.backendToken) return;
    const selected = selectedByMessage[msgIndex] || new Set();
    if (selected.size === 0) return;

    const toAdd = msg.startups.filter((_, i) => selected.has(i));
    setAdding(true);
    try {
      const result = await adminApi.scoutAdd(session.backendToken, toAdd);
      // Add a system-like message about what was added
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: result.message,
        },
      ]);
      setAddedMessages((prev) => new Set([...prev, msgIndex]));
      setSelectedByMessage((prev) => ({ ...prev, [msgIndex]: new Set() }));
      scrollToBottom();
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `Error adding startups: ${err instanceof Error ? err.message : "Unknown error"}`,
        },
      ]);
      scrollToBottom();
    } finally {
      setAdding(false);
    }
  }

  async function handleSend() {
    const text = input.trim();
    if (!text || loading || !session?.backendToken) return;

    setInput("");
    const userMsg: ChatMessage = { role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    scrollToBottom();

    setLoading(true);
    try {
      // Build history from previous messages (without startups data)
      const history = messages.map((m) => ({ role: m.role, content: m.content }));
      const result = await adminApi.scoutChat(session.backendToken, text, history);

      const assistantMsg: ChatMessage = {
        role: "assistant",
        content: result.reply,
        startups: result.startups.length > 0 ? result.startups : undefined,
      };
      setMessages((prev) => [...prev, assistantMsg]);

      // Auto-select all non-duplicate startups in the new message
      if (result.startups.length > 0) {
        const newMsgIndex = messages.length + 1; // +1 for user msg we just added
        setSelectedByMessage((prev) => ({
          ...prev,
          [newMsgIndex]: new Set(
            result.startups
              .map((s: StartupCandidate, i: number) => (!s.already_on_platform ? i : -1))
              .filter((i: number) => i >= 0),
          ),
        }));
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `Error: ${err instanceof Error ? err.message : "Failed to reach the scout agent"}`,
        },
      ]);
    } finally {
      setLoading(false);
      scrollToBottom();
      inputRef.current?.focus();
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 flex flex-col h-screen">
        {/* Header */}
        <div className="shrink-0 border-b border-border px-6 py-4 flex items-start justify-between">
          <div>
            <h2 className="font-serif text-xl text-text-primary">Scout</h2>
            <p className="text-sm text-text-tertiary mt-0.5">
              Find startups with AI-powered web search. Results go to triage for review.
            </p>
          </div>
          {messages.length > 0 && (
            <button
              onClick={() => {
                setMessages([]);
                setSelectedByMessage({});
                setAddedMessages(new Set());
                localStorage.removeItem(STORAGE_KEY);
              }}
              className="text-xs text-text-tertiary hover:text-text-primary transition mt-1"
            >
              Clear chat
            </button>
          )}
        </div>

        {/* Messages area */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <div className="font-serif text-2xl text-text-primary mb-2">What startups are you looking for?</div>
              <p className="text-sm text-text-tertiary mb-8 max-w-md">
                Ask me to find startups by batch (YC W25), sector (climate tech), geography, funding stage, or anything else.
              </p>
              <div className="grid grid-cols-2 gap-2 max-w-lg">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => {
                      setInput(s);
                      inputRef.current?.focus();
                    }}
                    className="text-left text-xs px-3 py-2 rounded border border-border text-text-secondary hover:border-accent hover:text-accent transition"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto space-y-4">
              {messages.map((msg, i) => (
                <div key={i}>
                  {msg.role === "user" ? (
                    <div className="flex justify-end">
                      <div className="bg-accent text-white rounded-2xl rounded-br-sm px-4 py-2 max-w-lg text-sm">
                        {msg.content}
                      </div>
                    </div>
                  ) : (
                    <div className="flex justify-start">
                      <div className="max-w-2xl">
                        <div className="bg-surface border border-border rounded-2xl rounded-bl-sm px-4 py-3 text-sm text-text-primary whitespace-pre-wrap">
                          {msg.content}
                        </div>
                        {msg.startups && msg.startups.length > 0 && !addedMessages.has(i) && (
                          <StartupResults
                            startups={msg.startups}
                            selected={selectedByMessage[i] || new Set()}
                            onToggle={(si) => toggleSelection(i, si)}
                            onSelectAll={() => toggleSelectAll(i, msg.startups!.length)}
                            onAddSelected={() => handleAddSelected(i)}
                            adding={adding}
                          />
                        )}
                        {addedMessages.has(i) && (
                          <div className="mt-2 text-xs text-score-high flex items-center gap-1">
                            <span>{"\u2713"}</span> Added to triage
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}
              {loading && (
                <div className="flex justify-start">
                  <div className="bg-surface border border-border rounded-2xl rounded-bl-sm px-4 py-3 text-sm text-text-tertiary">
                    <span className="inline-flex gap-1">
                      <span className="animate-pulse">Searching</span>
                      <span className="animate-pulse" style={{ animationDelay: "0.2s" }}>.</span>
                      <span className="animate-pulse" style={{ animationDelay: "0.4s" }}>.</span>
                      <span className="animate-pulse" style={{ animationDelay: "0.6s" }}>.</span>
                    </span>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input area */}
        <div className="shrink-0 border-t border-border px-6 py-4">
          <div className="max-w-3xl mx-auto flex gap-2">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Find YC W25 AI startups..."
              rows={1}
              className="flex-1 bg-surface border border-border rounded-lg px-4 py-2.5 text-sm text-text-primary placeholder:text-text-tertiary focus:border-accent focus:ring-1 focus:ring-accent outline-none resize-none"
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || loading}
              className="shrink-0 px-4 py-2.5 bg-accent text-white text-sm rounded-lg hover:bg-accent-hover disabled:opacity-40 transition"
            >
              {loading ? "..." : "Send"}
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
