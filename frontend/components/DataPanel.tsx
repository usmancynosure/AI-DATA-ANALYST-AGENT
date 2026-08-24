"use client";

import { useRef, useState } from "react";
import { connectDatabase, uploadFile } from "@/lib/api";
import type { SchemaInfo } from "@/lib/types";

interface Props {
  sessionId: string | null;
  schema: SchemaInfo | null;
  onSchema: (schema: SchemaInfo) => void;
  // Recreate the session (e.g. after a backend restart) and return the new id.
  onSessionExpired: () => Promise<string>;
}

function isExpiredSession(e: unknown): boolean {
  return /session not found/i.test(String(e instanceof Error ? e.message : e));
}

type Mode = "upload" | "connect";

export default function DataPanel({ sessionId, schema, onSchema, onSessionExpired }: Props) {
  const [mode, setMode] = useState<Mode>("upload");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [connUrl, setConnUrl] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  async function handleFile(file: File) {
    if (!sessionId) return;
    setBusy(true);
    setError(null);
    try {
      let res;
      try {
        res = await uploadFile(sessionId, file);
      } catch (e) {
        if (!isExpiredSession(e)) throw e;
        // Backend restarted → recreate the session and retry once.
        res = await uploadFile(await onSessionExpired(), file);
      }
      onSchema(res.schema_info);
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  }

  async function handleConnect() {
    if (!sessionId || !connUrl.trim()) return;
    setBusy(true);
    setError(null);
    try {
      let res;
      try {
        res = await connectDatabase(sessionId, connUrl.trim());
      } catch (e) {
        if (!isExpiredSession(e)) throw e;
        res = await connectDatabase(await onSessionExpired(), connUrl.trim());
      }
      onSchema(res.schema_info);
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside className="flex h-full w-80 shrink-0 flex-col gap-4 border-r border-border bg-panel/60 p-4">
      <div>
        <h2 className="text-sm font-semibold text-white">Data source</h2>
        <p className="mt-1 text-xs text-slate-500">
          Upload a CSV/Excel file or connect a database.
        </p>
      </div>

      <div className="flex rounded-lg bg-black/30 p-1 text-xs">
        {(["upload", "connect"] as Mode[]).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={`flex-1 rounded-md px-2 py-1.5 capitalize transition ${
              mode === m ? "bg-accent text-white" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            {m === "upload" ? "Upload file" : "Connect DB"}
          </button>
        ))}
      </div>

      {mode === "upload" ? (
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            const f = e.dataTransfer.files?.[0];
            if (f) handleFile(f);
          }}
          onClick={() => fileRef.current?.click()}
          className={`cursor-pointer rounded-xl border-2 border-dashed p-6 text-center text-xs transition ${
            dragging ? "border-accent bg-accent/10" : "border-border hover:border-slate-600"
          }`}
        >
          <input
            ref={fileRef}
            type="file"
            accept=".csv,.tsv,.txt,.xlsx,.xls"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleFile(f);
            }}
          />
          <div className="text-2xl">⬆</div>
          <p className="mt-2 text-slate-300">Drop a file or click to browse</p>
          <p className="mt-1 text-slate-600">.csv .tsv .xlsx .xls</p>
        </div>
      ) : (
        <div className="space-y-2">
          <input
            value={connUrl}
            onChange={(e) => setConnUrl(e.target.value)}
            placeholder="postgres://user:pass@host:5432/db"
            className="w-full rounded-lg border border-border bg-black/30 px-3 py-2 text-xs text-slate-200 outline-none focus:border-accent"
          />
          <button
            onClick={handleConnect}
            disabled={busy || !connUrl.trim()}
            className="w-full rounded-lg bg-accent px-3 py-2 text-xs font-medium text-white transition hover:bg-indigo-500 disabled:opacity-40"
          >
            Connect
          </button>
          <p className="text-[11px] leading-relaxed text-slate-600">
            Tip: use a read-only DB user. postgres:// and mysql:// are supported.
          </p>
        </div>
      )}

      {busy && <p className="text-xs text-slate-400">Loading data…</p>}
      {error && (
        <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</p>
      )}

      <SchemaView schema={schema} />
    </aside>
  );
}

function SchemaView({ schema }: { schema: SchemaInfo | null }) {
  if (!schema || schema.tables.length === 0) {
    return (
      <div className="mt-2 flex-1 rounded-lg border border-dashed border-border/60 p-4 text-center text-xs text-slate-600">
        No tables yet. Add data to explore its schema.
      </div>
    );
  }
  return (
    <div className="mt-2 flex-1 overflow-y-auto">
      <div className="mb-2 flex items-center justify-between text-[11px] uppercase tracking-wide text-slate-500">
        <span>Schema</span>
        <span className="rounded bg-black/30 px-1.5 py-0.5">{schema.dialect}</span>
      </div>
      <div className="space-y-3">
        {schema.tables.map((t) => (
          <div key={t.name} className="rounded-lg border border-border bg-black/20 p-2.5">
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs font-semibold text-emerald-300">{t.name}</span>
              {t.row_count != null && (
                <span className="text-[10px] text-slate-500">{t.row_count} rows</span>
              )}
            </div>
            <ul className="mt-1.5 space-y-0.5">
              {t.columns.map((c) => (
                <li key={c.name} className="flex justify-between text-[11px]">
                  <span className="font-mono text-slate-300">{c.name}</span>
                  <span className="text-slate-600">{c.type}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}
