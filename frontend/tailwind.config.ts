import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "media",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        serif: ["var(--font-serif)", "Georgia", "serif"],
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "monospace"],
      },
      colors: {
        ink: "var(--ink)",
        paper: "var(--paper)",
        surface: "var(--surface)",
        warm: "var(--warm)",
        muted: "var(--muted)",
        line: "var(--line)",
        agents: {
          left: "var(--agent-left)",
          right: "var(--agent-right)",
          econ: "var(--agent-econ)",
          geo: "var(--agent-geo)",
          devil: "var(--agent-devil)",
        },
      },
      maxWidth: {
        content: "860px",
      },
      borderRadius: {
        DEFAULT: "2px",
      },
    },
  },
  plugins: [],
};

export default config;
