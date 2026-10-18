// The type for a Tailwind configuration object (gives autocomplete and checking).
import type { Config } from "tailwindcss";

const config: Config = {
  // Use the visitor's device setting (light/dark) instead of a manual toggle.
  darkMode: "media",
  // Tailwind scans these files for class names and only generates CSS for the ones it finds.
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    // "extend" adds to Tailwind's defaults instead of replacing them.
    extend: {
      // Font families: the CSS variables set by next/font in app/layout.tsx, with fallbacks.
      fontFamily: {
        serif: ["var(--font-serif)", "Georgia", "serif"],
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "monospace"],
      },
      // Colour names, each pointing at a CSS variable in globals.css (so dark mode can swap them).
      colors: {
        ink: "var(--ink)",
        paper: "var(--paper)",
        surface: "var(--surface)",
        warm: "var(--warm)",
        muted: "var(--muted)",
        line: "var(--line)",
        edge: "var(--edge)",
        focus: "var(--focus)",
        warn: "var(--warn)",
        ok: "var(--ok)",
        // One colour per analyst, used as e.g. "bg-agents-left".
        agents: {
          left: "var(--agent-left)",
          right: "var(--agent-right)",
          econ: "var(--agent-econ)",
          geo: "var(--agent-geo)",
          devil: "var(--agent-devil)",
        },
      },
      // Adds the "max-w-content" class: the 860px width of the main column.
      maxWidth: {
        content: "1120px",
        reading: "720px",
      },
      // Default corner rounding for the "rounded" class: a subtle 2px.
      borderRadius: {
        DEFAULT: "2px",
      },
    },
  },
  // No extra Tailwind plugins are used.
  plugins: [],
};

// Export the configuration so Tailwind can read it.
export default config;
