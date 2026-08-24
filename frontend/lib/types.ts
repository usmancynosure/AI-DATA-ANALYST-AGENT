export type AgentEventType =
  | "thinking"
  | "text"
  | "tool_use"
  | "tool_result"
  | "chart"
  | "final"
  | "error"
  | "done";

export interface AgentEvent {
  type: AgentEventType;
  text?: string | null;
  tool?: string | null;
  tool_input?: Record<string, unknown> | null;
  is_error?: boolean | null;
  artifacts?: Array<Record<string, unknown>> | null;
}

export interface ColumnInfo {
  name: string;
  type: string;
}

export interface TableInfo {
  name: string;
  columns: ColumnInfo[];
  row_count?: number | null;
  sample_rows: Record<string, unknown>[];
}

export interface SchemaInfo {
  dialect: string;
  tables: TableInfo[];
}

// One question-and-answer exchange in the chat, built up from streamed events.
export interface Turn {
  id: string;
  question: string;
  steps: AgentEvent[];
  charts: string[]; // base64 PNGs
  answer: string;
  running: boolean;
  error?: string;
}
