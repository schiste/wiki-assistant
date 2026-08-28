export default [
  {
    files: ['gadget/**/*.{cjs,js,mjs}'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'script',
      globals: {
        console: 'readonly',
        document: 'readonly',
        fetch: 'readonly',
        globalThis: 'readonly',
        jQuery: 'readonly',
        location: 'readonly',
        mediaWiki: 'readonly',
        mw: 'readonly',
        navigator: 'readonly',
        setInterval: 'readonly',
        setTimeout: 'readonly',
        URL: 'readonly',
        URLSearchParams: 'readonly',
        window: 'readonly',
        // `module` only, not `require`/`exports`: the one production pattern that needs it is
        // the `typeof module !== 'undefined'` UMD-lite export guard, letting one gadget file
        // work both as a plain browser <script> (module is undefined there, guard skips) and
        // as a `node --test`-loadable CommonJS module — no bundler, no second copy of the
        // logic. `require` stays out of this browser-scoped block; see the *.test.js override
        // below, which is genuinely Node-only code that never ships to the browser.
        module: 'readonly'
      }
    },
    rules: {
      eqeqeq: 'error',
      'no-undef': 'error',
      'no-unused-vars': ['error', { argsIgnorePattern: '^_' }]
    }
  },
  {
    files: ['gadget/**/*.test.{cjs,js,mjs}'],
    languageOptions: {
      globals: {
        require: 'readonly'
      }
    }
  }
];
