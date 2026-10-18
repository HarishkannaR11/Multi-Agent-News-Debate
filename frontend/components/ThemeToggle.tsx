// Runs in the browser: it reads and writes localStorage and the <html> attribute.
"use client";

import { useEffect, useState } from "react";
import { readTheme, writeTheme, type ThemeChoice } from "@/lib/storage";

// Cycle order for the button: follow the device, then light, then dark.
const NEXT: Record<ThemeChoice, ThemeChoice> = { auto: "light", light: "dark", dark: "auto" };
const LABEL: Record<ThemeChoice, string> = { auto: "Theme: follows your device", light: "Theme: light", dark: "Theme: dark" };

// A small button that switches between light, dark and "follow the device".
export function ThemeToggle() {
  // Unknown until mounted (the server cannot see localStorage), so the first render shows a neutral label.
  const [choice, setChoice] = useState<ThemeChoice | null>(null);
  useEffect(() => setChoice(readTheme()), []);

  function change() {
    const next = NEXT[choice ?? "auto"];
    setChoice(next);
    writeTheme(next);
    // "auto" removes the attribute so the device preference applies; the others set it explicitly.
    if (next === "auto") document.documentElement.removeAttribute("data-theme");
    else document.documentElement.setAttribute("data-theme", next);
  }

  const current = choice ?? "auto";
  return (
    <button
      type="button"
      onClick={change}
      aria-label={`${LABEL[current]}. Activate to change.`}
      title={LABEL[current]}
      className="inline-flex h-9 w-9 items-center justify-center rounded border border-edge text-ink hover:bg-surface"
    >
      {/* A half-filled circle for "auto", a sun for light, a moon for dark. Decorative: the label says it. */}
      <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
        {current === "auto" && (
          <>
            <circle cx="12" cy="12" r="8" />
            <path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor" />
          </>
        )}
        {current === "light" && (
          <>
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
          </>
        )}
        {current === "dark" && <path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z" />}
      </svg>
    </button>
  );
}
