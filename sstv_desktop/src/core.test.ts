/** The first tests in the shell (#144).
 *
 * These pin what `request` already does correctly, because a gate that has
 * only ever been pointed at bugs proves nothing about the day it goes green.
 * What it does correctly is turn the engine's structured errors into
 * something the window can tell apart -- a 409 from a 503 from a process
 * that is not running -- which is the whole of #151's premise and the part
 * of #145 that does work.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CoreError, getConfig, patchConfig, stopDecode } from "./core";

function respondWith(body: unknown, status = 200): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve({
        ok: status >= 200 && status < 300,
        status,
        json: () => Promise.resolve(body),
      } as Response),
    ),
  );
}

describe("when the engine is not there", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("says so in words, with something to do about it", async () => {
    // The engine is a separate process and "not running" is the first-run
    // state, not an exception. A stack trace here would be the window
    // blaming the operator for a thing the app is supposed to start.
    await expect(getConfig()).rejects.toThrow(CoreError);
    await expect(getConfig()).rejects.toMatchObject({
      code: "ENGINE_UNREACHABLE",
      message: expect.stringContaining("can't reach"),
      suggestedAction: expect.stringContaining("sstv-server"),
    });
  });
});

describe("when the engine refuses", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("keeps the engine's own sentence rather than inventing one", async () => {
    respondWith(
      {
        detail: {
          error: "CONCURRENT_OPERATION",
          message:
            "A decode is already running, and the radio can only do one " +
            "thing at a time. Stop it before starting another.",
          suggested_action: "Stop the active session before starting a new one.",
        },
      },
      409,
    );

    await expect(getConfig()).rejects.toMatchObject({
      code: "CONCURRENT_OPERATION",
      message: expect.stringContaining("one thing at a time"),
      suggestedAction: expect.stringContaining("Stop the active session"),
    });
  });

  it("carries a code the window can branch on", async () => {
    // Requirement 13: a propagation failure must render louder than good
    // news, which means the window has to be able to tell it apart from
    // every other failure without reading the prose.
    respondWith(
      {
        detail: {
          error: "space_weather_unavailable",
          message: "I couldn't reach the space weather service.",
        },
      },
      503,
    );

    await expect(getConfig()).rejects.toMatchObject({
      code: "space_weather_unavailable",
    });
  });

  it("still throws something legible when there is no detail object", async () => {
    // FastAPI's own validation errors are a list, not the engine's detail
    // shape. There is no good sentence to show, but there must be a code
    // path that does not crash the window.
    respondWith({ detail: [{ msg: "field required" }] }, 422);

    const error = await getConfig().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(CoreError);
    expect((error as CoreError).message).toContain("422");
  });
});

describe("when the engine agrees", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns the body", async () => {
    respondWith({ spyserver_host: "airspy.local", spyserver_port: 5555 });

    await expect(getConfig()).resolves.toMatchObject({
      spyserver_host: "airspy.local",
    });
  });

  it("sends JSON, and says that it did", async () => {
    respondWith({ spyserver_host: "airspy.local" });

    await patchConfig({ spyserver_host: "airspy.local" });

    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(init?.method).toBe("PATCH");
    expect(init?.body).toBe(JSON.stringify({ spyserver_host: "airspy.local" }));
    expect(
      (init?.headers as Record<string, string>)["content-type"],
    ).toBe("application/json");
  });

  it("survives a 204, which has no body to parse", async () => {
    // stopDecode is the one that returns 204. Calling .json() on it throws,
    // so the early return is load-bearing rather than an optimisation.
    respondWith(null, 204);

    await expect(stopDecode("abc")).resolves.toBeUndefined();
  });
});
