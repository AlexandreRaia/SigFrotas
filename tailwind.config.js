/** Tailwind (CLI independente, sem Node). Gerar o CSS: scripts\css.ps1 */
module.exports = {
  content: ['./templates/**/*.html', './apps/**/templates/**/*.html'],
  theme: {
    extend: {
      fontFamily: { sans: ['Inter', '"Segoe UI"', 'system-ui', 'Roboto', 'Arial', 'sans-serif'] },
      // Cores da identidade em variaveis (ver :root em static/src/input.css): cada prefeitura pode ter a sua.
      colors: {
        primaria: { 50: 'var(--p-50)', 100: 'var(--p-100)', 700: 'var(--p-700)', 800: 'var(--p-800)', 900: 'var(--p-900)' },
        slate: { 50: '#F7F9FC', 100: '#EEF2F7', 400: '#7A8699' },   // so estas tres; as demais slate sao as do Tailwind
      },
      boxShadow: { sm: '0 2px 8px 0 rgba(15, 23, 42, 0.06)' },
    },
  },
};
