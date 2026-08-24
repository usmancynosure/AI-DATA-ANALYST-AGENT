import type { AgentEvent, SchemaInfo } from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function jsonOrThrow(res: Response) {
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json();
}

export async function getHealth(): Promise<{
  status: string;
  model: string;
  agent_enabled: boolean;
}> {
  return jsonOrThrow(await fetch(`${API_BASE}/health`, { cache: "no-store" }));
}

export async function createSession(): Promise<{ session_id: string }> {
  return jsonOrThrow(await fetch(`${API_BASE}/sessions`, { method: "POST" }));
}

export async function uploadFile(
  sessionId: string,
  file: File,
): Promise<{ tables: string[]; schema_info: SchemaInfo }> {
  const form = new FormData();
  form.append("file", file);
  return jsonOrThrow(
    await fetch(`${API_BASE}/sessions/${sessionId}/upload`, {
      method: "POST",
      body: form,
    }),
  );
}

export async function connectDatabase(
  sessionId: string,
  connectionUrl: string,
  label?: string,
): Promise<{ tables: string[]; schema_info: SchemaInfo }> {
  return jsonOrThrow(
    await fetch(`${API_BASE}/sessions/${sessionId}/connect`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ connection_url: connectionUrl, label }),
    }),
  );
}

/** Stream agent events over SSE via a POST + ReadableStream. */
export async function* streamChat(
  sessionId: string,
  message: string,
  signal?: AbortSignal,
): AsyncGenerator<AgentEvent> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
    signal,
  });
  if (!res.ok || !res.body) {
    throw new Error(`Chat failed: ${res.status} ${res.statusText}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? ""; // keep incomplete trailing chunk

    for (const chunk of chunks) {
      const line = chunk.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      const payload = line.slice("data: ".length);
      try {
        yield JSON.parse(payload) as AgentEvent;
      } catch {
        /* skip malformed frame */
      }
    }
  }
}
