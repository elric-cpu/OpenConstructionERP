/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        oxblood: "#722F37",
        cream: "#F5F1E8",
        charcoal: "#2D2D2D",
        canvas: "#FAF8F3",
      },
      fontFamily: {
        heading: ["Libre Baskerville", "Georgia", "serif"],
        subheading: ["Montserrat", "Arial", "sans-serif"],
        body: ["Source Sans 3", "Arial", "sans-serif"],
      },
    },
  },
};
