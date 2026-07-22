import js from '@eslint/js'
import prettier from 'eslint-config-prettier'
import react from 'eslint-plugin-react'
import reactHooks from 'eslint-plugin-react-hooks'
import globals from 'globals'

export default [
  { ignores: ['dist/**', 'coverage/**', 'node_modules/**'] },
  js.configs.recommended,
  {
    files: ['**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: { ...globals.browser, ...globals.es2021 },
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    settings: { react: { version: 'detect' } },
    plugins: { react, 'react-hooks': reactHooks },
    rules: {
      ...react.configs.recommended.rules,
      ...react.configs['jsx-runtime'].rules,
      ...reactHooks.configs.recommended.rules,
      // The app passes plain props between its own components; adding
      // propTypes to every one of them would be noise, not safety.
      'react/prop-types': 'off',
      // Every data panel in this app follows the same shape: flip a loading
      // flag, fire the request, resolve into state, with a `cancelled` guard
      // in the cleanup. That is the documented React 18 fetch-in-effect
      // pattern and what the tests assert on; the React Compiler rule wants
      // it restructured around a framework loader this app doesn't have.
      'react-hooks/set-state-in-effect': 'off',
      'no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
    },
  },
  {
    files: ['**/*.test.{js,jsx}', 'src/test/**/*.{js,jsx}'],
    languageOptions: { globals: { ...globals.node, ...globals.browser } },
  },
  {
    files: ['*.config.js', 'postcss.config.js', 'tailwind.config.js'],
    languageOptions: { globals: globals.node },
  },
  prettier,
]
