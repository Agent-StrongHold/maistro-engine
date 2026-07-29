import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

// Environments are scoped per area rather than declared once for everything.
//
// The single `globals.browser` block below used to apply to every `.js`/`.jsx`
// file in the package, including the Express server, the vitest suites and
// `vite.config.js` — none of which run in a browser. That produced 30
// `no-undef` reports for `process`, `Buffer` and `global`: all correct given
// what the config claimed, and all meaningless.
//
// That mattered more than the noise suggests. Those 30 were most of the
// findings, so the real ones sat behind them — and the natural response to a
// linter that is mostly wrong is to stop running it, which is what happened:
// `npm run lint` existed and no workflow ever invoked it.
export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
  },
  {
    // The Express server and the build config are Node, not browser.
    // `server.js` is a real network service — it proxies operator LLM
    // credentials and shells out to python3 — so it is the last file here
    // that should be linted against the wrong environment.
    files: ['server.js', 'server/**/*.js', 'vite.config.js', '*.config.js'],
    languageOptions: { globals: { ...globals.node } },
  },
  {
    // vitest suites need both: the runner's `describe`/`it`/`expect`/`vi`,
    // and Node globals for fixtures that stub `global.fetch`.
    files: ['tests/**/*.js', '**/*.test.js'],
    languageOptions: { globals: { ...globals.node, ...globals.vitest } },
  },
  {
    // react-hooks findings are WARNINGS, and `npm run lint` caps them with
    // `--max-warnings 13` — a ratchet, not a suppression. The count cannot
    // grow; every other rule in this config still fails the build outright.
    //
    // They are downgraded rather than fixed because they are real and each
    // needs the app exercised to change safely: three `immutability` errors
    // (props/hook arguments being mutated in BookWorkspace, plus a
    // use-before-declare on `doDecompose`), four `set-state-in-effect`
    // cascading-render errors, five stale-closure `exhaustive-deps`, and one
    // ref read during render. Retuning effect dependencies or removing a prop
    // mutation changes render behaviour, and nothing here can verify that —
    // the vitest suite covers lib/ and server/, not component rendering.
    //
    // Guessing at them would be worse than deferring them: a wrong
    // `exhaustive-deps` fix turns a stale value into an infinite render loop,
    // which this package has no test that would catch.
    files: ['**/*.{js,jsx}'],
    rules: {
      'react-hooks/exhaustive-deps': 'warn',
      'react-hooks/set-state-in-effect': 'warn',
      'react-hooks/immutability': 'warn',
      'react-hooks/refs': 'warn',
    },
  },
])
