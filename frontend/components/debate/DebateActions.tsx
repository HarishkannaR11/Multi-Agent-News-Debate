// Runs in the browser: clipboard, share sheet and saved-debates storage.
"use client";

import { useEffect, useState } from "react";
import { isBookmarked, toggleBookmark } from "@/lib/storage";

const SECTIONS = [
  { id: "overview", label: "Overview" },
  { id: "perspectives", label: "Perspectives" },
  { id: "disagreements", label: "Disagreements" },
  { id: "verdict", label: "Verdict" },
  { id: "sources", label: "Sources" },
  { id: "followup", label: "Follow-up" },
];

// Copy link, save, share and jump-to links, kept in view while reading on larger screens.
export function DebateActions({ debateId, title }: { debateId: string; title: string }) {
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState<"idle" | "ok" | "failed">("idle");
  const [canShare, setCanShare] = useState(false);

  // Storage and the share sheet only exist in the browser.
  useEffect(() => {
    setSaved(isBookmarked(debateId));
    setCanShare(typeof navigator !== "undefined" && typeof navigator.share === "function");
  }, [debateId]);

  const url = () => `${window.location.origin}/debate/${encodeURIComponent(debateId)}`;

  async function copy() {
    try {
      await navigator.clipboard.writeText(url());
      setCopied("ok");
    } catch {
      setCopied("failed");
    }
    setTimeout(() => setCopied("idle"), 2500);
  }

  async function share() {
    try {
      await navigator.share({ title, url: url() });
    } catch {
      // the visitor closed the share sheet: nothing to do
    }
  }

  const button = "rounded border border-edge bg-surface px-3 py-1.5 font-sans text-sm text-ink hover:bg-paper";
  return (
    <div className="md:sticky md:top-[3.75rem] md:z-20 md:-mx-12 md:border-b md:border-line md:bg-paper/95 md:px-12 md:backdrop-blur">
      <div className="flex flex-wrap items-center gap-2 py-2.5">
        <button type="button" onClick={copy} className={button}>
          {copied === "ok" ? "Link copied" : copied === "failed" ? "Copy failed" : "Copy link"}
        </button>
        <span className="sr-only" role="status" aria-live="polite">
          {copied === "ok" ? "Link copied to the clipboard" : copied === "failed" ? "Could not copy the link" : ""}
        </span>
        <button
          type="button"
          aria-pressed={saved}
          onClick={() => setSaved(toggleBookmark(debateId))}
          className={button}
        >
          {saved ? "★ Saved" : "☆ Save"}
        </button>
        {canShare && (
          <button type="button" onClick={share} className={button}>
            Share
          </button>
        )}
        <a href="#verdict" className="rounded bg-ink px-3 py-1.5 font-sans text-sm font-medium text-paper hover:opacity-90">
          Jump to verdict
        </a>
        <nav aria-label="On this page" className="ml-auto hidden items-center gap-3 font-sans text-sm text-warm lg:flex">
          {SECTIONS.map((s) => (
            <a key={s.id} href={`#${s.id}`} className="hover:text-ink hover:underline">
              {s.label}
            </a>
          ))}
        </nav>
      </div>
    </div>
  );
}
