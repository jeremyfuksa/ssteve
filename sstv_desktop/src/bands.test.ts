/** A band is a frequency, and the app has to agree with the engine (#150).
 *
 * `decode/start` takes a band by name, so listening never needed this.
 * `config` stores a frequency, so *remembering* which band you were on
 * does: the app used to reopen on 20m whatever you had been listening to,
 * and "listening is one click from then on" is not true when the first
 * click is putting the band back.
 *
 * The table below is a second copy of `sdr/bands.py`. Two copies drift, so
 * the point of these tests is the seam: a frequency that is a preset must
 * round-trip to its own band, and one that is not must stay itself rather
 * than being rounded to the nearest button.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  BANDS,
  BAND_FREQUENCIES,
  bandFor,
  nearestBand,
  startSpyServerDecode,
} from "./core";

/** 14.233 MHz: the other common 20m SSTV frequency, and not a preset. */
const NOT_A_PRESET = 14_233_000;

describe("a saved frequency", () => {
  it.each(BANDS)("round-trips for %s", (band) => {
    expect(bandFor(BAND_FREQUENCIES[band])).toBe(band);
  });

  it("is not claimed by a band it merely sits near", () => {
    // 3 kHz from the 20m preset. Rounding it to 20m would quietly retune
    // the operator when they next opened the app.
    expect(bandFor(NOT_A_PRESET)).toBeUndefined();
  });

  it("still has a band to ask about propagation with", () => {
    // Propagation is reported per band and has no notion of an exact
    // frequency. This is the one place a nearest-match is right.
    expect(nearestBand(NOT_A_PRESET)).toBe("20m");
    expect(nearestBand(7_175_000)).toBe("40m");
  });
});

describe("the table itself", () => {
  it("carries every band the buttons offer", () => {
    for (const band of BANDS) {
      expect(BAND_FREQUENCIES[band]).toBeGreaterThan(0);
    }
    expect(Object.keys(BAND_FREQUENCIES).sort()).toEqual([...BANDS].sort());
  });

  it("matches the frequencies the engine resolves", () => {
    // Copied from sdr/bands.py. If the engine's table moves and this one
    // does not, an operator pressing 20m here and typing --band 20m at the
    // terminal land on different frequencies -- which is the exact thing
    // that file's docstring says must not happen.
    expect(BAND_FREQUENCIES).toEqual({
      "80m": 3_845_000,
      "40m": 7_171_000,
      "20m": 14_230_000,
      "15m": 21_340_000,
      "10m": 28_680_000,
    });
  });
});


describe("starting a listen", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function sent() {
    const [, init] = vi.mocked(fetch).mock.calls[0];
    return JSON.parse(String(init?.body)) as Record<string, unknown>;
  }

  function accept() {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          status: 201,
          json: () => Promise.resolve({ session_id: "s", state: "listening" }),
        } as Response),
      ),
    );
  }

  it("names the band when one is chosen", async () => {
    accept();
    await startSpyServerDecode("40m", 3600);
    expect(sent().band).toBe("40m");
  });

  it("says nothing about the band when a frequency is saved", async () => {
    // The engine falls back to spyserver_frequency_hz only when given
    // neither. Sending a band here would retune the operator to a preset
    // they did not ask for -- 14.230 instead of the 14.233 they saved.
    accept();
    await startSpyServerDecode(null, 3600);
    expect(sent()).not.toHaveProperty("band");
    expect(sent()).not.toHaveProperty("frequency_hz");
    expect(sent().source).toBe("spyserver");
  });
});
