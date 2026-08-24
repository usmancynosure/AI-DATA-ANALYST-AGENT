import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "#0b0c10",
        panel: "#14161d",
        border: "#242833",
        accent: "#6366f1",
      },
    },
  },
  plugins: [],
};

export default config;
