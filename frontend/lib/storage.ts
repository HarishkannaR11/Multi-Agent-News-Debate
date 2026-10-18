// Things remembered in this browser only (there are no accounts): saved debates, "my debates", the last tab read.
// Every access is wrapped in try/catch because storage can be blocked (private windows, strict settings).

const KEYS = { bookmarks: "counterpoint_bookmarks", mine: "counterpoint_my_debates", tab: "counterpoint_tab:", theme: "counterpoint_theme" };
const MAX_ITEMS = 50;

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // storage blocked: the feature simply does not persist
  }
}

// A stored list of ids, newest first. Damaged data gives an empty list.
export function readIdList(key: "bookmarks" | "mine"): string[] {
  try {
    const parsed: unknown = JSON.parse(read(KEYS[key]) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter((v): v is string => typeof v === "string").slice(0, MAX_ITEMS) : [];
  } catch {
    return [];
  }
}

// Adds an id at the front (removing an older copy) and keeps the list a sensible size.
export function addId(key: "bookmarks" | "mine", id: string): string[] {
  const next = [id, ...readIdList(key).filter((existing) => existing !== id)].slice(0, MAX_ITEMS);
  write(KEYS[key], JSON.stringify(next));
  return next;
}

export function removeId(key: "bookmarks" | "mine", id: string): string[] {
  const next = readIdList(key).filter((existing) => existing !== id);
  write(KEYS[key], JSON.stringify(next));
  return next;
}

export function isBookmarked(id: string): boolean {
  return readIdList("bookmarks").includes(id);
}

// Saves or un-saves a debate. Returns whether it is saved afterwards.
export function toggleBookmark(id: string): boolean {
  if (isBookmarked(id)) {
    removeId("bookmarks", id);
    return false;
  }
  addId("bookmarks", id);
  return true;
}

// The perspective tab a reader last opened in a debate (their reading position).
export function readTab(debateId: string): string | null {
  return read(KEYS.tab + debateId);
}

export function writeTab(debateId: string, persona: string): void {
  write(KEYS.tab + debateId, persona);
}

export type ThemeChoice = "auto" | "light" | "dark";

export function readTheme(): ThemeChoice {
  const value = read(KEYS.theme);
  return value === "light" || value === "dark" ? value : "auto";
}

export function writeTheme(choice: ThemeChoice): void {
  if (choice === "auto") {
    try {
      window.localStorage.removeItem(KEYS.theme);
    } catch {
      // ignore
    }
  } else {
    write(KEYS.theme, choice);
  }
}
