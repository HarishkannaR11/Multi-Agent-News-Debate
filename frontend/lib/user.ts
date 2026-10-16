// The name under which the id is stored in the browser's localStorage.
const KEY = "counterpoint_user_id";
// The id used when the browser does not allow storage.
const FALLBACK = "guest";

/**
 * A random per-browser id so opinion threads aren't shared by every visitor.
 * It is not authentication: anyone can send any id. Matches the backend's user_id pattern.
 */
// Returns this browser's anonymous user id, creating and saving one the first time.
export function getAnonymousUserId(): string {
  try {
    // Look for an id saved earlier.
    const existing = window.localStorage.getItem(KEY);
    // Reuse it if it exists and matches the pattern the backend accepts.
    if (existing && /^[A-Za-z0-9_-]{1,64}$/.test(existing)) return existing;
    // Otherwise make a new random id (a UUID).
    const created = window.crypto.randomUUID();
    // Save it so the same browser gets the same id next time.
    window.localStorage.setItem(KEY, created);
    // Return the new id.
    return created;
  } catch {
    return FALLBACK; // storage blocked or crypto unavailable (older browser, insecure context)
  }
}
