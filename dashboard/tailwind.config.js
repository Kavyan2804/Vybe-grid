module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: '#0B6E4F',
          hover: '#09583F',
          active: '#074532',
          light: '#E8F5EE',
        },
        provenance: {
          live: '#036B4E',
          forecast: '#1D4ED8',
          simulated: '#6D28D9',
          baseline: '#92400E',
        },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
      },
    },
  },
  plugins: [],
};

