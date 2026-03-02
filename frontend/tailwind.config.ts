import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}"
  ],
  theme: {
    extend: {
      colors: {
        sand: "#f3efe4",
        ember: "#20160f",
        mint: "#89f5c7",
        coral: "#f58d74",
        ocean: "#295065"
      }
    }
  },
  plugins: []
};

export default config;
