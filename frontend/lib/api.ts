// The shape of a full debate as the backend sends it.
export type Debate = {
  // Unique id like "2026-10-01:some-topic".
  id: string;
  // The day of the debate.
  date: string;
  // The one-sentence topic.
  topic: string;
  // Link to the original article (optional, so it may be missing).
  source_url?: string;
  // The article text used for the debate.
  news_context: string;
  // The moderator's final summary.
  verdict: string;
  // Each analyst's opening argument, keyed by analyst name.
  arguments: Record<string, string>;
  // Each analyst's rebuttal, keyed by analyst name.
  rebuttals: Record<string, string>;
  // Each analyst's bias score (0 to 1), keyed by analyst name.
  bias_scores: Record<string, number>;
  // Current stage, e.g. "done".
  status: string;
  // The moderator's question for the optional second round (empty when there was no extra round).
  focus?: string;
  // Each analyst's closing statement from that round, keyed by analyst name.
  crossfire?: Record<string, string>;
};

/** What GET /api/debates returns: enough for a list, without the full transcript. */
// A smaller version of Debate: just the six fields the archive list needs.
export type DebateSummary = Pick<Debate, "id" | "date" | "topic" | "verdict" | "status" | "bias_scores">;

// The reply the backend sends after the user submits an opinion.
export type OpinionResponse = {
  // What the user wrote.
  user_opinion: string;
  // The AI's reply.
  agent_response: string;
  // The follow-up question.
  followup: string;
  // How the AI classified the opinion (only these three values are allowed).
  mode: "AGREE" | "CHALLENGE" | "EXPAND";
  // When it was created.
  timestamp: string;
};

/** Keep in sync with MAX_OPINION_CHARS on the backend. */
// The maximum number of characters allowed in an opinion.
export const MAX_OPINION_CHARS = 1000;

// A special error type that also remembers the HTTP status code.
export class ApiError extends Error {
  // "public readonly status" automatically creates a read-only property named status.
  constructor(
    public readonly status: number,
    message: string
  ) {
    // Call the normal Error constructor with the message.
    super(message);
    // Give the error a recognisable name.
    this.name = "ApiError";
  }
}

/**
 * Base URL for REST calls. NEXT_PUBLIC_* values are inlined at build time.
 * Unset in production means same-origin (a load balancer routes /api and /ws to the backend);
 * unset in `next dev` means the local backend.
 */
// Works out the address that REST requests should go to.
export function apiBase(): string {
  // The address configured at build time (may be undefined or empty).
  const configured = process.env.NEXT_PUBLIC_API_URL;
  // If configured, use it, removing any trailing slashes.
  if (configured) return configured.replace(/\/+$/, "");
  // Otherwise: during local development use the local backend; in production use "" (same website address).
  return process.env.NODE_ENV === "development" ? "http://localhost:8000" : "";
}

/** WebSocket base: explicit override, else derived from the API base, else the page's own origin. */
// Works out the address that the WebSocket should connect to.
export function wsBase(): string {
  // Are we running in a browser (where "window" exists)?
  const hasWindow = typeof window !== "undefined";
  // Is the page itself loaded over secure https?
  const secure = hasWindow && window.location.protocol === "https:";
  // The explicitly configured WebSocket address, without trailing slashes ("" if none).
  let base = process.env.NEXT_PUBLIC_WS_URL?.replace(/\/+$/, "") ?? "";
  // No explicit address: derive one.
  if (!base) {
    // The REST address, if any.
    const api = apiBase();
    // Reuse it, turning "http" into "ws" (and "https" into "wss").
    if (api) base = api.replace(/^http/, "ws");
    // Otherwise use the page's own host with the right ws/wss scheme.
    else if (hasWindow) base = `${secure ? "wss" : "ws"}://${window.location.host}`;
  }
  // An https page may not open ws:// (mixed content), so upgrade the scheme.
  // On an https page, force the secure "wss:" scheme; otherwise return as is.
  return secure ? base.replace(/^ws:/, "wss:") : base;
}

// Extracts a human-readable error message from a failed response.
async function errorMessage(res: Response, fallback: string): Promise<string> {
  try {
    // Try to read the body as JSON.
    const body = await res.json();
    // FastAPI puts the message under "detail".
    const detail = body?.detail;
    // A simple text message: use it.
    if (typeof detail === "string") return detail;
    // A list of validation errors: use the first one's message.
    if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg);
  } catch {
    // not JSON; fall through
  }
  // Nothing usable found: use the fallback text.
  return fallback;
}

// Shared helper that sends a request to the backend and returns its JSON (T = the expected result type).
async function request<T>(path: string, init: RequestInit | undefined, fallback: string): Promise<T> {
  // Will hold the server's response.
  let res: Response;
  try {
    // Send the request to the base address + path, giving up after 60 seconds.
    res = await fetch(`${apiBase()}${path}`, { ...init, signal: AbortSignal.timeout(60_000) });
  } catch {
    // The request never reached the server (offline, timeout, blocked): throw a friendly error with status 0.
    throw new ApiError(0, "Could not reach the server. Check your connection and try again.");
  }
  // The server answered with an error status: throw an error carrying its message.
  if (!res.ok) throw new ApiError(res.status, await errorMessage(res, fallback));
  // Success: return the parsed JSON.
  return res.json();
}

// Gets the list of debate summaries (up to "limit" of them).
export function fetchDebates(limit = 100): Promise<DebateSummary[]> {
  return request(`/api/debates?limit=${limit}`, undefined, "Failed to load debates");
}

// Gets one full debate; encodeURIComponent makes the id safe to put in a URL (the ":" becomes %3A).
export function fetchDebate(id: string): Promise<Debate> {
  return request(`/api/debate/${encodeURIComponent(id)}`, undefined, "Failed to load debate");
}

// Sends the user's opinion to the backend and returns the AI's reply.
export function submitOpinion(debateId: string, userId: string, opinion: string): Promise<OpinionResponse> {
  return request(
    // The endpoint for this debate.
    `/api/opinion/${encodeURIComponent(debateId)}`,
    {
      // Use the POST method (we are sending data).
      method: "POST",
      // Tell the server the body is JSON.
      headers: { "Content-Type": "application/json" },
      // The body: the user's id and opinion, as JSON text.
      body: JSON.stringify({ user_id: userId, opinion }),
    },
    // Message used if the server gives no better one.
    "Could not reach the debate agents. Try again."
  );
}

/** The user's earlier opinions on this debate, oldest first. */
// Loads the opinions this user already submitted for a debate.
export function fetchOpinions(debateId: string, userId: string): Promise<OpinionResponse[]> {
  return request(
    // Both ids are URL-encoded to be safe.
    `/api/opinions/${encodeURIComponent(debateId)}?user_id=${encodeURIComponent(userId)}`,
    undefined,
    "Failed to load your earlier opinions"
  );
}

// One message received over the WebSocket (every field is optional because different messages carry different fields).
export type DebateStreamEvent = {
  node?: string;
  // Set when something went wrong (e.g. "not_found").
  error?: string;
  // Human-readable explanation for the error.
  message?: string;
  debate_id?: string;
  topic?: string;
  // The stage: "debating", "rebuttal" or "done".
  status?: string;
  // The openings (the server calls this field "data").
  data?: Record<string, string>;
  rebuttals?: Record<string, string>;
  verdict?: string;
  bias_scores?: Record<string, number>;
  // The optional second round: the moderator's question and the analysts' answers.
  focus?: string;
  crossfire?: Record<string, string>;
};

// The states the WebSocket connection can be in (used to show messages to the user).
export type ConnectionState = "connecting" | "open" | "reconnecting" | "failed";

// Give up after this many failed reconnect attempts.
const MAX_RECONNECTS = 5;

// How long to wait before reconnect attempt number "attempt" (1, 2, 3, ...).
export function reconnectDelayMs(attempt: number): number {
  // Doubles each time: 1s, 2s, 4s, 8s, ... but never more than 15 seconds.
  return Math.min(1000 * 2 ** (attempt - 1), 15_000);
}

/**
 * Stream a stored debate. The server replays it as debating -> rebuttal -> done, then closes.
 * A dropped connection is retried with backoff (a replay is idempotent for the UI); once the
 * debate is done or reported missing the socket is left closed.
 */
// Opens the WebSocket and calls the given functions as messages and connection changes arrive.
export function connectDebateStream(
  // Which debate to stream ("latest", a date, or a full id).
  debateId: string,
  // Function called for every message received.
  onEvent: (event: DebateStreamEvent) => void,
  // Optional function called whenever the connection state changes.
  onConnection?: (state: ConnectionState) => void
  // Returns an object with a close() function so the caller can stop everything.
): { close: () => void } {
  // The current WebSocket (null until the first one is created).
  let ws: WebSocket | null = null;
  // The pending reconnect timer, if any.
  let timer: ReturnType<typeof setTimeout> | undefined;
  // How many reconnect attempts have happened in a row.
  let attempt = 0;
  // True once the caller has asked us to stop.
  let stopped = false;
  // True once the debate finished (or was reported missing): no more reconnecting needed.
  let finished = false;

  // Opens a new WebSocket connection (used first, and again for each reconnect).
  const open = () => {
    // Tell the UI whether this is the first connection or a retry.
    onConnection?.(attempt === 0 ? "connecting" : "reconnecting");
    // Create the connection to /ws/debate/{id}.
    ws = new WebSocket(`${wsBase()}/ws/debate/${encodeURIComponent(debateId)}`);
    // When the connection is established, tell the UI.
    ws.onopen = () => onConnection?.("open");
    // When a message arrives...
    ws.onmessage = (message) => {
      // Will hold the parsed message.
      let event: DebateStreamEvent;
      try {
        // The message text is JSON; parse it.
        event = JSON.parse(message.data);
      } catch {
        // Not valid JSON: ignore it.
        return;
      }
      // An error or the final "done" message means the replay is over.
      if (event.error || event.status === "done") finished = true;
      // A healthy message resets the reconnect counter.
      if (!event.error) attempt = 0;
      // Pass the message to the caller.
      onEvent(event);
    };
    // When the connection closes...
    ws.onclose = () => {
      // ...do nothing if we stopped on purpose or the debate is complete.
      if (stopped || finished) return;
      // Too many failures in a row: report that we gave up.
      if (attempt >= MAX_RECONNECTS) {
        onConnection?.("failed");
        return;
      }
      // Count this attempt.
      attempt += 1;
      // Tell the UI we are reconnecting.
      onConnection?.("reconnecting");
      // Try again after a growing delay.
      timer = setTimeout(open, reconnectDelayMs(attempt));
    };
  };

  // Make the first connection right away.
  open();

  // Give the caller a way to stop streaming.
  return {
    // close(): stop reconnecting, cancel any pending timer, and close the socket.
    close: () => {
      stopped = true;
      clearTimeout(timer);
      ws?.close();
    },
  };
}
