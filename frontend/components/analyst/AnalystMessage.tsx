"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AnalystChart } from "./AnalystChart";
import type { AnalystChartConfig, AnalystCitation } from "@/lib/types";

interface Props {
  role: "user" | "assistant";
  content: string;
  charts?: AnalystChartConfig[] | null;
  citations?: AnalystCitation[] | null;
  isStreaming?: boolean;
}

export function AnalystMessage({ role, content, charts, citations, isStreaming }: Props) {
  const isUser = role === "user";

  return (
    <div className={`flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser && (
        <div className="flex-shrink-0 w-7 h-7 rounded-full bg-accent/10 text-accent flex items-center justify-center text-xs font-medium mt-1">
          DT
        </div>
      )}
      <div
        className={`max-w-[85%] rounded-lg px-4 py-3 ${
          isUser
            ? "bg-accent text-white"
            : "bg-surface border border-border text-text-primary"
        }`}
      >
        {isUser ? (
          <p className="text-sm whitespace-pre-wrap">{content}</p>
        ) : (
          <div className="text-sm prose-sm prose-invert max-w-none">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                p: ({ children }) => <p className="mb-2 leading-relaxed text-text-primary">{children}</p>,
                h1: ({ children }) => <h3 className="text-base font-medium text-text-primary mt-4 mb-2">{children}</h3>,
                h2: ({ children }) => <h4 className="text-sm font-medium text-text-primary mt-3 mb-1">{children}</h4>,
                h3: ({ children }) => <h5 className="text-sm font-medium text-text-secondary mt-2 mb-1">{children}</h5>,
                ul: ({ children }) => <ul className="list-disc ml-4 mb-2 space-y-1">{children}</ul>,
                ol: ({ children }) => <ol className="list-decimal ml-4 mb-2 space-y-1">{children}</ol>,
                li: ({ children }) => <li className="text-text-primary">{children}</li>,
                strong: ({ children }) => <strong className="font-medium text-text-primary">{children}</strong>,
                code: ({ children, className }) => {
                  const isBlock = className?.includes("language-");
                  return isBlock ? (
                    <pre className="bg-background rounded p-3 overflow-x-auto text-xs my-2">
                      <code>{children}</code>
                    </pre>
                  ) : (
                    <code className="bg-background px-1 py-0.5 rounded text-xs">{children}</code>
                  );
                },
                table: ({ children }) => (
                  <div className="overflow-x-auto my-2">
                    <table className="min-w-full text-xs border border-border">{children}</table>
                  </div>
                ),
                th: ({ children }) => <th className="border border-border bg-surface-alt px-2 py-1 text-left font-medium">{children}</th>,
                td: ({ children }) => <td className="border border-border px-2 py-1">{children}</td>,
              }}
            >
              {content}
            </ReactMarkdown>

            {isStreaming && (
              <span className="inline-block w-2 h-4 bg-accent/60 animate-pulse ml-0.5" />
            )}
          </div>
        )}

        {/* Charts */}
        {charts && charts.length > 0 && (
          <div className="mt-2">
            {charts.map((chart, i) => (
              <AnalystChart key={i} config={chart} />
            ))}
          </div>
        )}

        {/* Citations */}
        {citations && citations.length > 0 && (
          <div className="mt-3 pt-2 border-t border-border/50">
            <p className="text-[10px] text-text-tertiary mb-1">Sources</p>
            <div className="flex flex-wrap gap-1">
              {citations.map((cite, i) => (
                <a
                  key={i}
                  href={cite.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[10px] text-accent/70 hover:text-accent bg-accent/5 px-1.5 py-0.5 rounded"
                  title={cite.url}
                >
                  {cite.title || new URL(cite.url).hostname}
                </a>
              ))}
            </div>
          </div>
        )}
      </div>
      {isUser && (
        <div className="flex-shrink-0 w-7 h-7 rounded-full bg-accent text-white flex items-center justify-center text-xs font-medium mt-1">
          U
        </div>
      )}
    </div>
  );
}
