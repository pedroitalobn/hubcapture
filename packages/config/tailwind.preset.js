// Preset Tailwind compartilhado (Tailwind 4). Web estende este preset.
// Marca Hub Capture — sistema "Bancada": acento lime sobre abyssal ink.
/** @type {import('tailwindcss').Config} */
module.exports = {
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: "#cef79e",
          fg: "#222f30",
        },
        abyss: "#222f30",
        bone: "#f7f7f5",
        graphite: "#4d5757",
        lichen: "#c9cbbe",
        tissue: "#e7e8e1",
      },
    },
  },
  plugins: [],
};
