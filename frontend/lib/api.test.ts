import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  apiBase,
  connectDebateStream,
  fetchDebate,
  reconnectDelayMs,
  submitOpinion,
  wsBase,
} from "./api";

function setWindow(protocol: string, host: string) {
  vi.stubGlobal("window", { location: { protocol, host } });
}

beforeEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.stubEnv("NODE_ENV", "production");
});
afterEach(() => vi.useRealTimers());

describe("apiBase / wsBase", () => {
  it("is same-origin in production when unset", () => {
    expect(apiBase()).toBe("");
  });

  it("falls back to the local backend under `next dev`", () => {
    vi.stubEnv("NODE_ENV", "development");
    expect(apiBase()).toBe("http://localhost:8000");
  });

  it("trims trailing slashes and derives ws from the API url", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.com/");
    expect(apiBase()).toBe("https://api.example.com");
    expect(wsBase()).toBe("wss://api.example.com");
  });

  it("uses the page origin when nothing is configured", () => {
    setWindow("https:", "app.example.com");
    expect(wsBase()).toBe("wss://app.example.com");
    setWindow("http:", "localhost:3000");
    expect(wsBase()).toBe("ws://localhost:3000");
  });

  it("upgrades ws:// to wss:// on an https page (mixed content)", () => {
    vi.stubEnv("NEXT_PUBLIC_WS_URL", "ws://api.example.com");
    setWindow("https:", "app.example.com");
    expect(wsBase()).toBe("wss://api.example.com");
  });

  it("leaves ws:// alone on an http page", () => {
    vi.stubEnv("NEXT_PUBLIC_WS_URL", "ws://localhost:8000");
    setWindow("http:", "localhost:3000");
    expect(wsBase()).toBe("ws://localhost:8000");
  });
});

describe("requests", () => {
  const respond = (status: number, body: unknown) =>
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })));

  it("url-encodes debate ids", async () => {
    respond(200, {});
    await fetchDebate("2026-09-30:some-topic");
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe("/api/debate/2026-09-30%3Asome-topic");
  });

  it("surfaces the server's detail message", async () => {
    respond(429, { detail: "Too many requests. Try again shortly." });
    await expect(submitOpinion("latest", "u", "hi")).rejects.toMatchObject({
      status: 429,
      message: "Too many requests. Try again shortly.",
    });
  });

  it("reads the first message of a FastAPI validation error", async () => {
    respond(422, { detail: [{ msg: "String should have at most 1000 characters" }] });
    await expect(submitOpinion("latest", "u", "hi")).rejects.toThrow("at most 1000");
  });

  it("wraps network failures", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("failed")));
    const err = await fetchDebate("latest").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(0);
  });
});

class FakeSocket {
  static instances: FakeSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((m: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  close = vi.fn();
  constructor(public url: string) {
    FakeSocket.instances.push(this);
  }
  send(event: object) {
    this.onmessage?.({ data: JSON.stringify(event) });
  }
}

describe("connectDebateStream", () => {
  beforeEach(() => {
    FakeSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeSocket);
    vi.useFakeTimers();
    setWindow("https:", "app.example.com");
  });

  it("connects to the encoded id and forwards events", () => {
    const events: unknown[] = [];
    connectDebateStream("2026-09-30:t", (e) => events.push(e));
    expect(FakeSocket.instances[0].url).toBe("wss://app.example.com/ws/debate/2026-09-30%3At");
    FakeSocket.instances[0].send({ status: "debating" });
    expect(events).toEqual([{ status: "debating" }]);
  });

  it("ignores malformed frames", () => {
    const onEvent = vi.fn();
    connectDebateStream("latest", onEvent);
    FakeSocket.instances[0].onmessage?.({ data: "not json" });
    expect(onEvent).not.toHaveBeenCalled();
  });

  it("reconnects with backoff after a drop, then gives up", () => {
    const states: string[] = [];
    connectDebateStream("latest", vi.fn(), (s) => states.push(s));

    for (let attempt = 1; attempt <= 5; attempt++) {
      FakeSocket.instances.at(-1)!.onclose?.();
      vi.advanceTimersByTime(reconnectDelayMs(attempt));
      expect(FakeSocket.instances).toHaveLength(attempt + 1);
    }
    FakeSocket.instances.at(-1)!.onclose?.();
    vi.advanceTimersByTime(60_000);

    expect(FakeSocket.instances).toHaveLength(6);
    expect(states.at(-1)).toBe("failed");
  });

  it("does not reconnect once the debate is done", () => {
    connectDebateStream("latest", vi.fn());
    FakeSocket.instances[0].send({ status: "done" });
    FakeSocket.instances[0].onclose?.();
    vi.advanceTimersByTime(60_000);
    expect(FakeSocket.instances).toHaveLength(1);
  });

  it("does not reconnect after a not-found error", () => {
    const onEvent = vi.fn();
    connectDebateStream("nope", onEvent);
    FakeSocket.instances[0].send({ error: "not_found", message: "No debate found for this id." });
    FakeSocket.instances[0].onclose?.();
    vi.advanceTimersByTime(60_000);
    expect(FakeSocket.instances).toHaveLength(1);
    expect(onEvent).toHaveBeenCalledOnce();
  });

  it("stops retrying after close()", () => {
    const stream = connectDebateStream("latest", vi.fn());
    FakeSocket.instances[0].onclose?.();
    stream.close();
    vi.advanceTimersByTime(60_000);
    expect(FakeSocket.instances).toHaveLength(1);
  });

  it("caps the backoff", () => {
    expect([1, 2, 3, 4, 5, 10].map(reconnectDelayMs)).toEqual([1000, 2000, 4000, 8000, 15000, 15000]);
  });
});
