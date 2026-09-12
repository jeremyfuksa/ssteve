// jsdom has no canvas and no WebSocket worth the name. Rather than mock the
// whole browser, each test stubs what it needs; this file only adds the DOM
// matchers and undoes anything a test left behind.
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
