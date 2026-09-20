const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";

export type Debate = {
  id: string;
  date: string;
  topic: string;
  news_context: string;
  verdict: string;
  arguments: Record<string, string>;
  rebuttals: Record<string, string>;
  bias_scores: Record<string, number>;
  status: string;
};

export type OpinionResponse = {
  user_opinion: string;
  agent_response: string;
  followup: string;
  mode: "AGREE" | "CHALLENGE" | "EXPAND";
  timestamp: string;
};

export async function fetchDebates(): Promise<Debate[]> {
  const res = await fetch(`${API_URL}/api/debates`);
  if (!res.ok) throw new Error("Failed to load debates");
  return res.json();
}

export async function fetchDebate(id: string): Promise<Debate> {
  const res = await fetch(`${API_URL}/api/debate/${id}`);
  if (!res.ok) throw new Error("Failed to load debate");
  return res.json();
}

export async function submitOpinion(
  debateId: string,
  userId: string,
  opinion: string
): Promise<OpinionResponse> {
  const res = await fetch(`${API_URL}/api/opinion/${debateId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, opinion }),
  });
  if (!res.ok) throw new Error("Failed to submit opinion");
  return res.json();
}

export type DebateStreamEvent = {
  node: string;
  status?: string;
  data: Record<string, string>;
  verdict?: string;
  bias_scores?: Record<string, number>;
};

export function connectDebateStream(
  debateId: string,
  onEvent: (event: DebateStreamEvent) => void
): WebSocket {
  const ws = new WebSocket(`${WS_URL}/ws/debate/${debateId}`);
  ws.onmessage = (message) => {
    onEvent(JSON.parse(message.data));
  };
  return ws;
}
