import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#07080c",
        foreground: "#f3f4f6",
        surface: {
          950: "#07080c",
          900: "#0b0e14",
          850: "#10131d",
          800: "#161a27",
          750: "#1c2132",
          border: "#1e2436",
          "border-subtle": "#141724",
          "border-strong": "#2b334d",
        },
        violet: {
          300: "#ddd6fe",
          400: "#a78bfa",
          500: "#8b5cf6",
          600: "#7c3aed",
          700: "#6d28d9",
          800: "#5b21b6",
          900: "#2e1065",
          950: "#170b3b",
        },
        lavender: {
          200: "#e9d5ff",
          300: "#d8b4fe",
          400: "#c084fc",
          500: "#a855f7",
        },
        soc: {
          critical: "#f43f5e",
          "critical-bg": "#240b12",
          "critical-border": "#4a1220",
          high: "#f97316",
          "high-bg": "#251208",
          "high-border": "#4e230e",
          medium: "#eab308",
          "medium-bg": "#231a08",
          "medium-border": "#47350d",
          low: "#94a3b8",
          "low-bg": "#141722",
          "low-border": "#252c3f",
          info: "#818cf8",
          "info-bg": "#12142d",
          "info-border": "#272a5a",
          verified: "#10b981",
          "verified-bg": "#091e17",
          "verified-border": "#123c2e",
        },
        cyber: {
          dark: "#07080c",
          card: "#0f121c",
          border: "#1e2436",
          muted: "#64748b",
          neonGreen: "#10b981",
          neonCyan: "#8b5cf6",
          neonRose: "#f43f5e",
          neonAmber: "#f59e0b",
        },
      },
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          '"Segoe UI"',
          "Roboto",
          '"Helvetica Neue"',
          "Arial",
          "sans-serif",
        ],
        mono: [
          '"JetBrains Mono"',
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Monaco",
          "Consolas",
          "monospace",
        ],
      },
      boxShadow: {
        glow: "0 0 20px -5px rgba(124, 58, 237, 0.25)",
        "glow-sm": "0 0 10px -2px rgba(124, 58, 237, 0.2)",
      },
    },
  },
  plugins: [],
};

export default config;

