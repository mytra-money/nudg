import preset, { content } from 'frappe-ui/tailwind'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.dirname(fileURLToPath(import.meta.url))
const whatsappUi = ['vendor/whatsapp-ui/src', '../../whatsapp/ui/src', '../../../whatsapp/ui/src']
  .map((entry) => path.resolve(root, entry))
  .find((entry) => fs.existsSync(path.join(entry, 'index.ts')))

/** @type {import('tailwindcss').Config} */
export default {
  presets: [preset],
  content: [
    ...content,
    './index.html',
    './src/**/*.{vue,js,ts,jsx,tsx}',
    ...(whatsappUi ? [path.join(whatsappUi, '**/*.{vue,js,ts,jsx,tsx}')] : []),
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'Helvetica', 'Arial', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
      },
      borderRadius: {
        none: '0px',
        sm: '4px',
        DEFAULT: '6px',
        md: '6px',
        lg: '8px',
        xl: '12px',
        '2xl': '16px',
        '3xl': '24px',
        full: '9999px',
      },
      colors: {
        emerald: {
          50: '#ecfdf5',
          100: '#d1fae5',
          200: '#a7f3d0',
          300: '#6ee7b7',
          400: '#34d399',
          500: '#10b981',
          600: '#059669',
          700: '#047857',
          800: '#065f46',
          900: '#064e3b',
        },
      },
    },
  },
}
