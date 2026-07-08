/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eff6ff",
          100: "#dbeafe",
          200: "#bfdbfe",
          300: "#93c5fd",
          400: "#60a5fa",
          500: "#3b82f6",
          600: "#2563eb",
          700: "#1d4ed8",
          800: "#1e40af",
          900: "#1e3a8a",
        },
        surface: {
          50: "#faf9f6",
          100: "#f5f3ef",
          200: "#ebe7de",
          300: "#d6cebc",
          400: "#b8ad94",
          500: "#a3987a",
          600: "#8b7f64",
          700: "#6d6350",
          800: "#5a5244",
          900: "#4a4339",
        },
      },
      fontFamily: {
        sans: [
          "Microsoft YaHei UI",
          "PingFang SC",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "sans-serif",
        ],
        mono: ["JetBrains Mono", "Cascadia Code", "SF Mono", "Consolas", "monospace"],
      },
      boxShadow: {
        'card': '0 1px 2px rgba(0,0,0,.04), 0 4px 16px rgba(0,0,0,.06)',
        'card-hover': '0 2px 4px rgba(0,0,0,.05), 0 8px 24px rgba(0,0,0,.08)',
        'input': '0 0 0 3px rgba(59,130,246,.12), 0 0 24px rgba(59,130,246,.08)',
        'button': '0 2px 8px rgba(37,99,235,.25)',
        'float': '0 8px 32px rgba(0,0,0,.1)',
      },
      animation: {
        "fade-in": "fadeIn 0.3s ease-out",
        "slide-up": "slideUp 0.35s cubic-bezier(0.16, 1, 0.3, 1)",
        "pulse-soft": "pulseSoft 1.8s ease-in-out infinite",
        "shimmer": "shimmer 2s linear infinite",
        "scale-in": "scaleIn 0.25s cubic-bezier(0.34, 1.56, 0.64, 1)",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        pulseSoft: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.55" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        scaleIn: {
          "0%": { opacity: "0", transform: "scale(0.9)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
      },
    },
  },
  plugins: [],
};
