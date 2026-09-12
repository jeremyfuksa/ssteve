// Lint for the shell (#144). Deliberately small: `tsc --noEmit` already
// carries the type rules, so this is only for what types cannot say.
//
// The rule set is the type-unaware `recommended`, on purpose. Turning on
// `recommendedTypeChecked` produced 51 errors, 40 of them `no-unsafe-*`
// against the `any` that `response.json()` returns -- a refactor of the
// client, not a gate on this change.
//
// Type-aware rules are turned on one at a time, as the defect each would
// flag is fixed, so that none of them lands as a warning nobody reads:
//
//   switch-exhaustiveness-check -- on since #145. The session and app event
//                                  unions are discriminated, so adding an
//                                  event type to the engine and not to the
//                                  window is a lint error rather than a
//                                  silent drop.
//   no-floating-promises        -- still off, pending #148:
//                                  `adjustDecode(...).catch(() => undefined)`
//                                  swallows a rejected PATCH, so a setting
//                                  the engine clamped shows as applied.

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

      // An error since #145 removed the last instance. Every one was an
      // `event as any` in the session-event switch, and they existed
      // because the event union was not discriminated.
      "@typescript-eslint/no-explicit-any": "error",

      // The reason the union is discriminated. A switch over it must
      // handle every member or say out loud that it is ignoring one.
      "@typescript-eslint/switch-exhaustiveness-check": [
        "error",
        { considerDefaultExhaustiveForUnions: true },
      ],

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
