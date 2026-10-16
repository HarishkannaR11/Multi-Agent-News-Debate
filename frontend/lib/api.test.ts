// Vitest tools: lifecycle hooks, test grouping (describe), a single test (it), assertions (expect), and mocks (vi).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
// The functions under test, from api.ts.
import {
  ApiError,
  apiBase,
  connectDebateStream,
  fetchDebate,
  fetchOpinions,
  reconnectDelayMs,
  submitOpinion,
  wsBase,
} from "./api";

// Pretends a browser "window" exists with the given page protocol and host (tests run in plain Node, which has none).
function setWindow(protocol: string, host: string) {
  vi.stubGlobal("window", { location: { protocol, host } });
}

// Before every test: undo any fake env vars and globals from the previous test, then pretend we are in production.
beforeEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.stubEnv("NODE_ENV", "production");
});
// After every test: switch back to real timers in case a test used fake ones.
afterEach(() => vi.useRealTimers());

// Tests for how the REST and WebSocket base addresses are worked out.
describe("apiBase / wsBase", () => {
  it("is same-origin in production when unset", () => {
    // No env var + production = an empty string, meaning "the same website address".
    expect(apiBase()).toBe("");
  });

  it("falls back to the local backend under `next dev`", () => {
    // Pretend we are running the development server.
    vi.stubEnv("NODE_ENV", "development");
    expect(apiBase()).toBe("http://localhost:8000");
  });

  it("trims trailing slashes and derives ws from the API url", () => {
    // Configure an API address that ends with a slash.
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.com/");
    // The slash is removed...
    expect(apiBase()).toBe("https://api.example.com");
    // ...and the WebSocket address is derived from it (https becomes wss).
    expect(wsBase()).toBe("wss://api.example.com");
  });

  it("uses the page origin when nothing is configured", () => {
    // On an https page the WebSocket address uses wss and the page's host.
    setWindow("https:", "app.example.com");
    expect(wsBase()).toBe("wss://app.example.com");
    // On an http page it uses plain ws.
    setWindow("http:", "localhost:3000");
    expect(wsBase()).toBe("ws://localhost:3000");
  });

  it("upgrades ws:// to wss:// on an https page (mixed content)", () => {
    // An insecure ws:// address is configured, but the page itself is https.
    vi.stubEnv("NEXT_PUBLIC_WS_URL", "ws://api.example.com");
    setWindow("https:", "app.example.com");
    // The browser would block it, so the code upgrades it to wss.
    expect(wsBase()).toBe("wss://api.example.com");
  });

  it("leaves ws:// alone on an http page", () => {
    // Both the address and the page are insecure, so nothing changes.
    vi.stubEnv("NEXT_PUBLIC_WS_URL", "ws://localhost:8000");
    setWindow("http:", "localhost:3000");
    expect(wsBase()).toBe("ws://localhost:8000");
  });
});

// Tests for the REST helper functions.
describe("requests", () => {
  // Helper: replace the global fetch with a fake that answers with the given status and JSON body.
  const respond = (status: number, body: unknown) =>
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })));

  it("url-encodes debate ids", async () => {
    // The server's reply content does not matter here.
    respond(200, {});
    await fetchDebate("2026-09-30:some-topic");
    // The first argument of the first fetch call is the URL; ":" must have become "%3A".
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe("/api/debate/2026-09-30%3Asome-topic");
  });

  it("encodes both the debate id and the user id when loading opinion history", async () => {
    respond(200, []);
    await fetchOpinions("2026-09-30:some-topic", "u-1");
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe("/api/opinions/2026-09-30%3Asome-topic?user_id=u-1");
  });

  it("surfaces the server's detail message", async () => {
    // The server answers 429 (rate limited) with a readable message.
    respond(429, { detail: "Too many requests. Try again shortly." });
    // The error thrown should carry the same status code and message.
    await expect(submitOpinion("latest", "u", "hi")).rejects.toMatchObject({
      status: 429,
      message: "Too many requests. Try again shortly.",
    });
  });

  it("reads the first message of a FastAPI validation error", async () => {
    // FastAPI sends validation problems as a list of objects with a "msg" field.
    respond(422, { detail: [{ msg: "String should have at most 1000 characters" }] });
    // The thrown error's message should contain that first "msg".
    await expect(submitOpinion("latest", "u", "hi")).rejects.toThrow("at most 1000");
  });

  it("wraps network failures", async () => {
    // Make fetch itself fail, as if the network were down.
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("failed")));
    // Catch the error and return it so we can inspect it.
    const err = await fetchDebate("latest").catch((e) => e);
    // It should be our own ApiError with status 0 (meaning "never reached the server").
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(0);
  });
});

// A stand-in for the browser's WebSocket so the tests can control exactly when messages and closes happen.
class FakeSocket {
  // Remembers every socket created, so tests can find them.
  static instances: FakeSocket[] = [];
  // The same event hooks the real WebSocket has; the code under test fills them in.
  onopen: (() => void) | null = null;
  onmessage: ((m: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  // A spy function: records whether close() was called.
  close = vi.fn();
  // Records the address it was asked to connect to ("public url" auto-creates the property).
  constructor(public url: string) {
    // Register this new socket in the list.
    FakeSocket.instances.push(this);
  }
  // Test helper: pretend the server sent this event (as JSON text) to the page.
  send(event: object) {
    this.onmessage?.({ data: JSON.stringify(event) });
  }
}

// Tests for the WebSocket stream helper.
describe("connectDebateStream", () => {
  // Before each test in this group:
  beforeEach(() => {
    // Forget sockets from earlier tests.
    FakeSocket.instances = [];
    // Make the code use our fake instead of the real WebSocket.
    vi.stubGlobal("WebSocket", FakeSocket);
    // Control time manually so reconnect delays do not make tests slow.
    vi.useFakeTimers();
    // Pretend the page is https://app.example.com.
    setWindow("https:", "app.example.com");
  });

  it("connects to the encoded id and forwards events", () => {
    // Collect every event the helper passes on.
    const events: unknown[] = [];
    connectDebateStream("2026-09-30:t", (e) => events.push(e));
    // The first socket should have been opened at the right, URL-encoded address.
    expect(FakeSocket.instances[0].url).toBe("wss://app.example.com/ws/debate/2026-09-30%3At");
    // Simulate the server sending a message.
    FakeSocket.instances[0].send({ status: "debating" });
    // The helper should have forwarded it unchanged.
    expect(events).toEqual([{ status: "debating" }]);
  });

  it("ignores malformed frames", () => {
    const onEvent = vi.fn();
    connectDebateStream("latest", onEvent);
    // Deliver text that is not valid JSON.
    FakeSocket.instances[0].onmessage?.({ data: "not json" });
    // The callback must not be called (and nothing may crash).
    expect(onEvent).not.toHaveBeenCalled();
  });

  it("reconnects with backoff after a drop, then gives up", () => {
    // Record every connection state the helper reports.
    const states: string[] = [];
    connectDebateStream("latest", vi.fn(), (s) => states.push(s));

    // Five times in a row: drop the newest connection, wait the expected delay, and expect one more socket.
    // (".at(-1)" means "the last item"; "!" tells TypeScript it is definitely there.)
    for (let attempt = 1; attempt <= 5; attempt++) {
      FakeSocket.instances.at(-1)!.onclose?.();
      vi.advanceTimersByTime(reconnectDelayMs(attempt));
      expect(FakeSocket.instances).toHaveLength(attempt + 1);
    }
    // A sixth drop: the helper should give up instead of reconnecting.
    FakeSocket.instances.at(-1)!.onclose?.();
    // Even after a long wait, no new socket appears.
    vi.advanceTimersByTime(60_000);

    // 1 original + 5 reconnects = 6 sockets, and the last reported state is "failed".
    expect(FakeSocket.instances).toHaveLength(6);
    expect(states.at(-1)).toBe("failed");
  });

  it("does not reconnect once the debate is done", () => {
    connectDebateStream("latest", vi.fn());
    // The server says the debate is done, then the connection closes normally.
    FakeSocket.instances[0].send({ status: "done" });
    FakeSocket.instances[0].onclose?.();
    vi.advanceTimersByTime(60_000);
    // Still only the original socket.
    expect(FakeSocket.instances).toHaveLength(1);
  });

  it("does not reconnect after a not-found error", () => {
    const onEvent = vi.fn();
    connectDebateStream("nope", onEvent);
    // The server reports that the debate does not exist, then closes.
    FakeSocket.instances[0].send({ error: "not_found", message: "No debate found for this id." });
    FakeSocket.instances[0].onclose?.();
    vi.advanceTimersByTime(60_000);
    // No reconnect, and the error was delivered to the caller exactly once.
    expect(FakeSocket.instances).toHaveLength(1);
    expect(onEvent).toHaveBeenCalledOnce();
  });

  it("stops retrying after close()", () => {
    const stream = connectDebateStream("latest", vi.fn());
    // The connection drops, so a reconnect timer is scheduled...
    FakeSocket.instances[0].onclose?.();
    // ...but the caller closes the stream before it fires.
    stream.close();
    vi.advanceTimersByTime(60_000);
    // The timer was cancelled, so no new socket was created.
    expect(FakeSocket.instances).toHaveLength(1);
  });

  it("caps the backoff", () => {
    // Delays double each time but never exceed 15 seconds.
    expect([1, 2, 3, 4, 5, 10].map(reconnectDelayMs)).toEqual([1000, 2000, 4000, 8000, 15000, 15000]);
  });
});
