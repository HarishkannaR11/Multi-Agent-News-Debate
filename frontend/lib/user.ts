const KEY = "counterpoint_user_id";
const FALLBACK = "guest";

/**
 * A random per-browser id so opinion threads aren't shared by every visitor.
 * It is not authentication: anyone can send any id. Matches the backend's user_id pattern.
 */
export function getAnonymousUserId(): string {
  try {
    const existing = window.localStorage.getItem(KEY);
    if (existing && /^[A-Za-z0-9_-]{1,64}$/.test(existing)) return existing;
    const created = window.crypto.randomUUID();
    window.localStorage.setItem(KEY, created);
    return created;
  } catch {
    return FALLBACK; // storage blocked or crypto unavailable (older browser, insecure context)
  }
}
