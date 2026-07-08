/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    screens: {
      sm: "640px",
      md: "768px",
      lg: "1024px",
      xl: "1280px",
      laptop: "1400px",
      "2xl": "1536px",
    },
    extend: {
      colors: {
        primary: {
          DEFAULT: "#2563eb",
          light: "#eff6ff",
          dark: "#1d4ed8",
        },
        success: {
          DEFAULT: "#059669",
          light: "#ecfdf5",
        },
        warning: {
          DEFAULT: "#f59e0b",
          light: "#fffbeb",
        },
        danger: {
          DEFAULT: "#e11d48",
          light: "#fff1f2",
        },
        info: {
          DEFAULT: "#0ea5e9",
          light: "#f0f9ff",
        },
      },
      fontFamily: {
        sans: ["Inter", "PingFang SC", "HarmonyOS Sans", "Microsoft YaHei", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      borderRadius: {
        sm: "0.375rem",
        md: "0.5rem",
        lg: "0.75rem",
        xl: "1rem",
      },
      boxShadow: {
        soft: "0 1px 2px 0 rgb(15 23 42 / 0.06)",
        card: "0 1px 2px 0 rgb(15 23 42 / 0.06)",
        "card-hover": "0 4px 12px 0 rgb(15 23 42 / 0.08)",
        "card-elevated": "0 8px 24px 0 rgb(15 23 42 / 0.1)",
      },
    },
  },
  plugins: [],
};
