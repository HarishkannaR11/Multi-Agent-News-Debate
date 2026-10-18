// Marks this file as a client component: it uses state and the browser's clipboard.
"use client";

// useState keeps the "copied" flag and re-draws the button when it changes.
import { useState } from "react";

// A small button that copies the permanent address of one debate, so a reader can share it.
export function CopyLinkButton({ debateId }: { debateId: string }) {
  // True for two seconds after a successful copy.
  const [copied, setCopied] = useState(false);

  // Copies "<this website>/debate/<id>" to the clipboard.
  async function copy() {
    try {
      // The id contains ":", so it is URL-encoded just like the archive links.
      await navigator.clipboard.writeText(`${window.location.origin}/debate/${encodeURIComponent(debateId)}`);
      // Show the confirmation, and hide it again after two seconds.
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access can be blocked (insecure page, denied permission); the button then simply does nothing.
    }
  }

  return (
    // aria-live announces the change from "Copy link" to "Link copied" to screen readers.
    <button
      onClick={copy}
      aria-live="polite"
      className="font-sans text-xs uppercase tracking-[0.04em] text-muted hover:text-ink hover:underline"
    >
      {copied ? "Link copied" : "Copy link"}
    </button>
  );
}
