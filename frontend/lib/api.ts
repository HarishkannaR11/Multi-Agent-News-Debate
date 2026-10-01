export type Debate = {
  id: string;
  date: string;
  topic: string;
  source_url?: string;
  news_context: string;
  verdict: string;
  arguments: Record<string, string>;
  rebuttals: Record<string, string>;
  bias_scores: Record<string, number>;
  status: string;
};

/** What GET /api/debates returns: enough for a list, without the full transcript. */
export type DebateSummary = Pick<Debate, "id" | "date" | "topic" | "verdict" | "status" | "bias_scores">;

export type OpinionResponse = {
  user_opinion: string;
  agent_response: string;
  followup: string;
  mode: "AGREE" | "CHALLENGE" | "EXPAND";
  timestamp: string;
};

/** Keep in sync with MAX_OPINION_CHARS on the backend. */
export const MAX_OPINION_CHARS = 1000;

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * Base URL for REST calls. NEXT_PUBLIC_* values are inlined at build time.
 * Unset in production means same-origin (a load balancer routes /api and /ws to the backend);
 * unset in `next dev` means the local backend.
 */
export function apiBase(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL;
  if (configured) return configured.replace(/\/+$/, "");
  return process.env.NODE_ENV === "development" ? "http://localhost:8000" : "";
}

/** WebSocket base: explicit override, else derived from the API base, else the page's own origin. */
export function wsBase(): string {
  const hasWindow = typeof window !== "undefined";
  const secure = hasWindow && window.location.protocol === "https:";
  let base = process.env.NEXT_PUBLIC_WS_URL?.replace(/\/+$/, "") ?? "";
  if (!base) {
    const api = apiBase();
    if (api) base = api.replace(/^http/, "ws");
    else if (hasWindow) base = `${secure ? "wss" : "ws"}://${window.location.host}`;
  }
  // An https page may not open ws:// (mixed content), so upgrade the scheme.
  return secure ? base.replace(/^ws:/, "wss:") : base;
}

async function errorMessage(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg);
  } catch {
    // not JSON; fall through
  }
  return fallback;
}

async function request<T>(path: string, init: RequestInit | undefined, fallback: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${apiBase()}${path}`, { ...init, signal: AbortSignal.timeout(60_000) });
  } catch {
    throw new ApiError(0, "Could not reach the server. Check your connection and try again.");
  }
  if (!res.ok) throw new ApiError(res.status, await errorMessage(res, fallback));
  return res.json();
}

export function fetchDebates(limit = 100): Promise<DebateSummary[]> {
  return request(`/api/debates?limit=${limit}`, undefined, "Failed to load debates");
}

export function fetchDebate(id: string): Promise<Debate> {
  return request(`/api/debate/${encodeURIComponent(id)}`, undefined, "Failed to load debate");
}

export function submitOpinion(debateId: string, userId: string, opinion: string): Promise<OpinionResponse> {
  return request(
    `/api/opinion/${encodeURIComponent(debateId)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId, opinion }),
    },
    "Could not reach the debate agents. Try again."
  );
}

/** The user's earlier opinions on this debate, oldest first. */
export function fetchOpinions(debateId: string, userId: string): Promise<OpinionResponse[]> {
  return request(
    `/api/opinions/${encodeURIComponent(debateId)}?user_id=${encodeURIComponent(userId)}`,
    undefined,
    "Failed to load your earlier opinions"
  );
}

export type DebateStreamEvent = {
  node?: string;
  error?: string;
  message?: string;
  debate_id?: string;
  topic?: string;
  status?: string;
  data?: Record<string, string>;
  rebuttals?: Record<string, string>;
  verdict?: string;
  bias_scores?: Record<string, number>;
};

export type ConnectionState = "connecting" | "open" | "reconnecting" | "failed";

const MAX_RECONNECTS = 5;

export function reconnectDelayMs(attempt: number): number {
  return Math.min(1000 * 2 ** (attempt - 1), 15_000);
}

/**
 * Stream a stored debate. The server replays it as debating -> rebuttal -> done, then closes.
 * A dropped connection is retried with backoff (a replay is idempotent for the UI); once the
 * debate is done or reported missing the socket is left closed.
 */
export function connectDebateStream(
  debateId: string,
  onEvent: (event: DebateStreamEvent) => void,
  onConnection?: (state: ConnectionState) => void
): { close: () => void } {
  let ws: WebSocket | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let attempt = 0;
  let stopped = false;
  let finished = false;

  const open = () => {
    onConnection?.(attempt === 0 ? "connecting" : "reconnecting");
    ws = new WebSocket(`${wsBase()}/ws/debate/${encodeURIComponent(debateId)}`);
    ws.onopen = () => onConnection?.("open");
    ws.onmessage = (message) => {
      let event: DebateStreamEvent;
      try {
        event = JSON.parse(message.data);
      } catch {
        return;
      }
      if (event.error || event.status === "done") finished = true;
      if (!event.error) attempt = 0;
      onEvent(event);
    };
    ws.onclose = () => {
      if (stopped || finished) return;
      if (attempt >= MAX_RECONNECTS) {
        onConnection?.("failed");
        return;
      }
      attempt += 1;
      onConnection?.("reconnecting");
      timer = setTimeout(open, reconnectDelayMs(attempt));
    };
  };

  open();

  return {
    close: () => {
      stopped = true;
      clearTimeout(timer);
      ws?.close();
    },
  };
}
