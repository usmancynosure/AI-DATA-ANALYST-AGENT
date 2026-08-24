export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function getHealth(): Promise<{
  status: string;
  model: string;
  agent_enabled: boolean;
}> {
  const res = await fetch(`${API_BASE}/health`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Backend returned ${res.status}`);
  return res.json();
}
