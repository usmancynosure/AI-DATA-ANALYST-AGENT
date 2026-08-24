"use client";

import { useEffect, useRef, useState } from "react";
import ChatPanel from "@/components/ChatPanel";
import DataPanel from "@/components/DataPanel";
import { createSession, getHealth, streamChat } from "@/lib/api";
import type { SchemaInfo, Turn } from "@/lib/types";

export default function Home() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [schema, setSchema] = useState<SchemaInfo | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [running, setRunning] = useState(false);
  const [boot, setBoot] = useState<{ ok: boolean; agent: boolean; error?: string } | null>(null);
  const idRef = useRef(0);

  useEffect(() => {
    (async () => {
      try {
        const health = await getHealth();
        const s = await createSession();
        setSessionId(s.session_id);
        setBoot({ ok: true, agent: health.agent_enabled });
      } catch (e) {
        setBoot({ ok: false, agent: false, error: String(e instanceof Error ? e.message : e) });
      }
    })();
  }, []);

  async function ask(message: string) {
    if (!sessionId || running) return;
    const id = `t${idRef.current++}`;
    const turn: Turn = { id, question: message, steps: [], charts: [], answer: "", running: true };
    setTurns((prev) => [...prev, turn]);
    setRunning(true);

    const patch = (fn: (t: Turn) => Turn) =>
      setTurns((prev) => prev.map((t) => (t.id === id ? fn(t) : t)));

    try {
      for await (const ev of streamChat(sessionId, message)) {
        if (ev.type === "done") break;
        if (ev.type === "chart" && ev.artifacts?.[0]?.image) {
          patch((t) => ({ ...t, charts: [...t.charts, ev.artifacts![0].image as string] }));
        } else if (ev.type === "final") {
          patch((t) => ({ ...t, answer: ev.text ?? "" }));
        } else if (ev.type === "error") {
          patch((t) => ({ ...t, error: ev.text ?? "Something went wrong." }));
        } else {
          patch((t) => ({ ...t, steps: [...t.steps, ev] }));
        }
      }
    } catch (e) {
      patch((t) => ({ ...t, error: String(e instanceof Error ? e.message : e) }));
    } finally {
      patch((t) => ({ ...t, running: false }));
      setRunning(false);
    }
  }

  const hasData = !!schema && schema.tables.length > 0;

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center justify-between border-b border-border bg-panel/60 px-5 py-3">
        <div className="flex items-center gap-2">
          <span className="text-lg">📊</span>
          <h1 className="text-sm font-semibold text-white">AI Data Analyst Agent</h1>
        </div>
        <BootStatus boot={boot} />
      </header>

      <div className="flex min-h-0 flex-1">
        <DataPanel sessionId={sessionId} schema={schema} onSchema={setSchema} />
        <ChatPanel
          turns={turns}
          onAsk={ask}
          disabled={!sessionId || !hasData || running}
          running={running}
          hasData={hasData}
        />
      </div>
    </div>
  );
}

function BootStatus({
  boot,
}: {
  boot: { ok: boolean; agent: boolean; error?: string } | null;
}) {
  if (boot === null) return <span className="text-xs text-slate-500">connecting…</span>;
  if (!boot.ok)
    return (
      <span className="flex items-center gap-1.5 text-xs text-red-400">
        <span className="h-2 w-2 rounded-full bg-red-400" /> backend offline
      </span>
    );
  return (
    <span className="flex items-center gap-1.5 text-xs text-slate-400">
      <span className="h-2 w-2 rounded-full bg-emerald-400" />
      {boot.agent ? "agent ready" : "data layer only (no API key)"}
    </span>
  );
}
