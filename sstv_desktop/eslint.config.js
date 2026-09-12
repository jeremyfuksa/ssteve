// Lint for the shell (#144). Deliberately small: `tsc --noEmit` already
// carries the type rules, so this is only for what types cannot say.
//
// The rule set is the type-unaware `recommended`, on purpose. Turning on
// `recommendedTypeChecked` produced 51 errors, 40 of them `no-unsafe-*`
// against the `any` that `response.json()` returns -- a refactor of the
// client, not a gate on this change.
//
// Two type-aware rules are worth having and are deliberately absent until
// the defects they would flag are fixed, so that neither lands as a
// warning nobody reads:
//
//   no-floating-promises        -- #148: `adjustDecode(...).catch(() => undefined)`
//                                  swallows a rejected PATCH, so a setting the
//                                  engine clamped shows as applied.
//   switch-exhaustiveness-check -- #145: the session event switch has no
//                                  default and silently drops seven of the
//                                  engine's twelve event types.
//
// Turn each on in the PR that fixes its defect.

import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: ["dist", "src-tauri/target", "coverage"],
  },
  js.configs.recommended,
  {
    // Type-aware rules only where there are types. Spreading these at the
    // top level made eslint try to type-check its own config file.
    files: ["**/*.{ts,tsx}"],
    extends: [...tseslint.configs.recommended],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    plugins: {
      "react-hooks": reactHooks,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,

      // Warn, not error, and only until #145. Every instance is an
      // `event as any` in the session-event switch, which exists because
      // the event union is not discriminated -- the same root cause as
      // #145's "every spec event rendered or explicitly ignored in one
      // place". Typing the union removes all of them at once, and this
      // becomes an error in that PR. Left visible rather than disabled so
      // the count going up is noticeable.
      "@typescript-eslint/no-explicit-any": "warn",

      // Unused arguments are usually a signature being ignored; a leading
      // underscore is how you say you meant it.
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
    },
  },
  {
    files: ["**/*.test.{ts,tsx}", "**/test/**"],
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
    rules: {
      // Tests reach into shapes on purpose.
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/no-unsafe-assignment": "off",
      "@typescript-eslint/no-unsafe-member-access": "off",
      "@typescript-eslint/no-unsafe-argument": "off",
      "@typescript-eslint/no-unsafe-call": "off",
    },
  },
);
