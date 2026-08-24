"use client";

import { useState } from "react";
import type { AgentEvent } from "@/lib/types";

const TOOL_LABELS: Record<string, string> = {
  get_schema: "Inspecting schema",
  run_sql: "Querying data",
  run_python: "Running analysis",
};

export default function AgentTimeline({ steps }: { steps: AgentEvent[] }) {
  const visible = steps.filter((s) =>
    ["thinking", "tool_use", "tool_result"].includes(s.type),
  );
  if (visible.length === 0) return null;

  return (
    <ol className="space-y-1.5 border-l border-border pl-4">
      {visible.map((step, i) => (
        <Step key={i} step={step} />
      ))}
    </ol>
  );
}

function Step({ step }: { step: AgentEvent }) {
  const [open, setOpen] = useState(false);

  if (step.type === "thinking") {
    return (
      <li className="relative">
        <Dot className="bg-slate-500" />
        <button
          onClick={() => setOpen((o) => !o)}
          className="text-xs italic text-slate-500 hover:text-slate-300"
        >
          {open ? "▾" : "▸"} thinking
        </button>
        {open && (
          <p className="mt-1 whitespace-pre-wrap rounded bg-black/30 p-2 text-[11px] text-slate-400">
            {step.text}
          </p>
        )}
      </li>
    );
  }

  if (step.type === "tool_use") {
    const label = TOOL_LABELS[step.tool ?? ""] ?? step.tool;
    const sql =
      (step.tool_input?.query as string) ||
      (step.tool_input?.code as string) ||
      "";
    return (
      <li className="relative">
        <Dot className="bg-accent" />
        <div className="text-xs text-slate-300">
          <span className="font-medium text-indigo-300">{label}</span>
        </div>
        {sql && (
          <pre className="mt-1 max-h-40 overflow-auto rounded bg-black/40 p-2 font-mono text-[11px] text-slate-300">
            {sql}
          </pre>
        )}
      </li>
    );
  }

  // tool_result
  return (
    <li className="relative">
      <Dot className={step.is_error ? "bg-red-400" : "bg-emerald-400"} />
      <button
        onClick={() => setOpen((o) => !o)}
        className={`text-xs ${step.is_error ? "text-red-300" : "text-slate-500"} hover:text-slate-300`}
      >
        {open ? "▾" : "▸"} {step.is_error ? "error" : "result"}
      </button>
      {open && step.text && (
        <pre className="mt-1 max-h-48 overflow-auto rounded bg-black/30 p-2 font-mono text-[11px] text-slate-400">
          {step.text}
        </pre>
      )}
    </li>
  );
}

function Dot({ className }: { className: string }) {
  return (
    <span
      className={`absolute -left-[21px] top-1 h-2 w-2 rounded-full ring-4 ring-bg ${className}`}
    />
  );
}
