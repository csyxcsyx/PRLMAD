/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html',
    './static/js/**/*.js',
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#fbf1ed',
          100: '#f5dfd7',
          200: '#ebc2b3',
          300: '#dfa18b',
          400: '#d4876c',
          500: '#cc785c',
          600: '#b96449',
          700: '#a9583e',
          800: '#864735',
          900: '#6d3c30',
        },
      },
    },
  },
  safelist: [
    'rotate-180',
    'opacity-50',
    'text-emerald-700',
    'text-red-500',
    'text-red-600',
    'bg-emerald-50',
    'bg-amber-50',
    'border-emerald-100',
    'border-amber-100',
  ],
};
