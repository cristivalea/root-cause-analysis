import type { Config } from "tailwindcss";

// Every colour is a CSS variable (src/styles/tokens.css), so the palette is changed in one place.
const token = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: token("brand-50"), 100: token("brand-100"), 600: token("brand-600"),
          700: token("brand-700"), 800: token("brand-800"), 950: token("brand-950"),
        },
        bg: token("bg"),
        surface: token("surface"),
        line: token("line"),
        ink: token("ink"),
        muted: token("muted"),
        success: { DEFAULT: token("success"), soft: token("success-soft") },
        warning: { DEFAULT: token("warning"), soft: token("warning-soft") },
        danger: { DEFAULT: token("danger"), soft: token("danger-soft") },
        info: { DEFAULT: token("info"), soft: token("info-soft") },
        neutral: { soft: token("neutral-soft") },
      },
      fontFamily: { sans: ["'Inter Variable'", "system-ui", "sans-serif"] },
      borderRadius: { control: "8px", card: "12px" },
      boxShadow: {
        card: "0 1px 2px rgb(16 24 40 / 0.06)",
        pop: "0 8px 24px rgb(16 24 40 / 0.10)",
      },
      maxWidth: { content: "1280px" },
      keyframes: {
        // the individual translate / scale properties, so an animation never overrides an element's own transform
        "fade-up": { from: { opacity: "0", translate: "0 6px" }, to: { opacity: "1", translate: "0 0" } },
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        "scale-in": { from: { opacity: "0", scale: "0.97" }, to: { opacity: "1", scale: "1" } },
      },
      animation: {
        "fade-up": "fade-up 240ms ease-out both",
        "fade-in": "fade-in 150ms ease-out both",
        "scale-in": "scale-in 180ms ease-out both",
      },
    },
  },
  plugins: [],
} satisfies Config;
