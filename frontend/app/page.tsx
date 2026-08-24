"use client";

import { useEffect, useState } from "react";
import { getHealth } from "@/lib/api";

type Status = { ok: boolean; model?: string; agentEnabled?: boolean; error?: string };

export default function Home() {
  const [status, setStatus] = useState<Status | null>(null);

  useEffect(() => {
    getHealth()
      .then((h) =>
        setStatus({ ok: h.status === "ok", model: h.model, agentEnabled: h.agent_enabled })
      )
      .catch((e) => setStatus({ ok: false, error: String(e) }));
  }, []);

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center gap-8 px-6">
      <div>
        <h1 className="text-3xl font-semibold text-white">AI Data Analyst Agent</h1>
        <p className="mt-2 text-slate-400">
          Upload a CSV or connect a database, ask questions in plain English, and get SQL,
          Python analysis, and charts.
        </p>
      </div>

      <div className="rounded-xl border border-border bg-panel p-5">
        <h2 className="text-sm font-medium uppercase tracking-wide text-slate-500">
          Backend status
        </h2>
        {status === null ? (
          <p className="mt-2 text-slate-400">Checking…</p>
        ) : status.ok ? (
          <div className="mt-2 space-y-1">
            <p className="flex items-center gap-2 text-emerald-400">
              <span className="h-2 w-2 rounded-full bg-emerald-400" /> Connected
            </p>
            <p className="text-sm text-slate-400">Model: {status.model}</p>
            <p className="text-sm text-slate-400">
              Agent: {status.agentEnabled ? "enabled" : "no API key (data layer only)"}
            </p>
          </div>
        ) : (
          <div className="mt-2">
            <p className="flex items-center gap-2 text-red-400">
              <span className="h-2 w-2 rounded-full bg-red-400" /> Not reachable
            </p>
            <p className="mt-1 text-sm text-slate-500">{status.error}</p>
          </div>
        )}
      </div>

      <p className="text-sm text-slate-600">
        Chat, uploads, and visualizations land in Phase 5. This page verifies the frontend ↔
        backend wiring.
      </p>
    </main>
  );
}
