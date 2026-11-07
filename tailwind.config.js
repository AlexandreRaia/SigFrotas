/** Tailwind (CLI independente, sem Node). Gerar o CSS: scripts\css.ps1 */
// Escala de cinza em variaveis (ver --g-* em static/src/input.css): o tema escuro troca os valores e as classes gray-/slate- acompanham.
const cinza = Object.fromEntries([50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950].map((n) => [n, `var(--g-${n})`]));

module.exports = {
  // os .py de templatetags entram porque escolhem classes (ex.: o selo colorido de cada situacao)
  content: ['./templates/**/*.html', './apps/**/templates/**/*.html', './apps/**/templatetags/*.py'],
  theme: {
    extend: {
      fontFamily: { sans: ['"Segoe UI"', 'system-ui', '-apple-system', 'Roboto', '"Helvetica Neue"', 'Arial', 'sans-serif'] },
      // Cores da identidade em variaveis (ver :root em static/src/input.css): cada prefeitura pode ter a sua.
      colors: {
        primaria: { 50: 'var(--p-50)', 100: 'var(--p-100)', 700: 'var(--p-700)', 800: 'var(--p-800)', 900: 'var(--p-900)', hover: 'var(--p-hover)' },
        // O sistema usa a escala de cinza do design (gray do Tailwind) tambem sob o nome "slate", que ja esta nos templates.
        gray: cinza,
        slate: cinza,
        fundo: 'var(--fundo)',
      },
      boxShadow: { sm: 'none' },   // visual plano: sem sombras
    },
  },
};
