// Preset Tailwind compartilhado (Tailwind 4). Web estende este preset.
// Marca Hub Capture: amarelo (systemYellow) sobre branco (light) / preto (dark).
/** @type {import('tailwindcss').Config} */
module.exports = {
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: "#ffd60a",
          soft: "#ffe45c",
          deep: "#e6b400",
          fg: "#171207",
        },
      },
    },
  },
  plugins: [],
};
