"use client";

import { useEffect, useRef, useState } from "react";
import type { Turn } from "@/lib/types";
import AgentTimeline from "./AgentTimeline";

interface Props {
  turns: Turn[];
  onAsk: (message: string) => void;
  disabled: boolean;
  running: boolean;
  hasData: boolean;
}

const SUGGESTIONS = [
  "What are the top 5 rows by the main numeric column?",
  "Summarize this dataset and its key statistics.",
  "Show the trend over time as a chart.",
];

export default function ChatPanel({ turns, onAsk, disabled, running, hasData }: Props) {
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  function submit(text: string) {
    const msg = text.trim();
    if (!msg || disabled) return;
    onAsk(msg);
    setInput("");
  }

  return (
    <div className="flex h-full flex-1 flex-col">
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-6">
        <div className="mx-auto max-w-3xl space-y-8">
          {turns.length === 0 && (
            <div className="mt-16 text-center">
              <h1 className="text-2xl font-semibold text-white">Ask your data anything</h1>
              <p className="mt-2 text-sm text-slate-400">
                {hasData
                  ? "Ask a question in plain English — the agent writes SQL, runs Python, and charts the answer."
                  : "Add a data source on the left to get started."}
              </p>
              {hasData && (
                <div className="mt-6 flex flex-wrap justify-center gap-2">
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s}
                      onClick={() => submit(s)}
                      className="rounded-full border border-border bg-panel px-3 py-1.5 text-xs text-slate-300 transition hover:border-accent hover:text-white"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {turns.map((turn) => (
            <TurnView key={turn.id} turn={turn} />
          ))}
        </div>
      </div>

      <div className="border-t border-border bg-panel/40 px-6 py-4">
        <div className="mx-auto flex max-w-3xl items-end gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit(input);
              }
            }}
            rows={1}
            placeholder={hasData ? "Ask a question…" : "Add data to begin"}
            disabled={disabled}
            className="max-h-40 flex-1 resize-none rounded-xl border border-border bg-black/30 px-4 py-3 text-sm text-slate-100 outline-none placeholder:text-slate-600 focus:border-accent disabled:opacity-50"
          />
          <button
            onClick={() => submit(input)}
            disabled={disabled || !input.trim()}
            className="rounded-xl bg-accent px-4 py-3 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:opacity-40"
          >
            {running ? "…" : "Ask"}
          </button>
        </div>
      </div>
    </div>
  );
}

function TurnView({ turn }: { turn: Turn }) {
  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-accent px-4 py-2 text-sm text-white">
          {turn.question}
        </div>
      </div>

      <div className="rounded-2xl rounded-bl-sm border border-border bg-panel px-4 py-3">
        <AgentTimeline steps={turn.steps} />

        {turn.charts.length > 0 && (
          <div className="mt-3 space-y-3">
            {turn.charts.map((img, i) => (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                key={i}
                src={`data:image/png;base64,${img}`}
                alt="chart"
                className="max-w-full rounded-lg border border-border bg-white"
              />
            ))}
          </div>
        )}

        {turn.answer && (
          <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-slate-100">
            {turn.answer}
          </p>
        )}

        {turn.running && !turn.answer && (
          <p className="mt-2 flex items-center gap-2 text-xs text-slate-500">
            <span className="h-2 w-2 animate-pulse rounded-full bg-accent" /> working…
          </p>
        )}

        {turn.error && (
          <p className="mt-2 rounded bg-red-500/10 px-3 py-2 text-xs text-red-300">
            {turn.error}
          </p>
        )}
      </div>
    </div>
  );
}
