/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          bg: "#f5f0e8",
          forest: "#293d07",
          "forest-hover": "#1c2b05",
          cream: "#fbf9f4",
          paper: "#ffffff",
          accent: "#4d5b31",
          gold: "#bda55d",
        }
      },
      fontFamily: {
        sans: ["Plus Jakarta Sans", "Inter", "sans-serif"],
        serif: ["Playfair Display", "serif"],
      }
    },
  },
  plugins: [],
}
