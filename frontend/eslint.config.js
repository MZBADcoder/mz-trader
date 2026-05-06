import js from '@eslint/js'
import importPlugin from 'eslint-plugin-import'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import globals from 'globals'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    plugins: {
      import: importPlugin,
    },
    languageOptions: {
      globals: globals.browser,
    },
    settings: {
      'import/resolver': {
        node: {
          paths: ['src'],
          extensions: ['.js', '.jsx', '.ts', '.tsx'],
        },
      },
    },
    rules: {
      'import/no-restricted-paths': [
        'error',
        {
          zones: [
            {
              target: './src/shared',
              from: ['./src/entities', './src/features', './src/widgets', './src/pages', './src/app'],
            },
            {
              target: './src/entities',
              from: ['./src/features', './src/widgets', './src/pages', './src/app'],
            },
            {
              target: './src/features',
              from: ['./src/widgets', './src/pages', './src/app'],
            },
            {
              target: './src/widgets',
              from: ['./src/pages', './src/app'],
            },
            {
              target: './src/pages',
              from: ['./src/app'],
            },
          ],
        },
      ],
    },
  },
])

