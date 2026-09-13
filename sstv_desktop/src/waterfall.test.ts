/** Sync reads differently from a loud bin (#147, frontend-contract §20.4).
 *
 * The engine has carried `sync_detected` on every spectrum frame since it
 * was added, with a comment citing §20.4, and the strip never read it. A
 * sync pulse and a strong carrier painted identically -- both just bright
 * amber -- which is precisely the confusion the field exists to prevent:
 * an operator uses sync to confirm they are tuned, and "something loud is
 * there" is not that.
 *
 * These test the column rather than the canvas. jsdom has no 2D context,
 * so a test that drew would assert nothing; the column is where the
 * behaviour is.
 */

import { describe, expect, it } from "vitest";

import { SYNC_TICK_PX, paintColumn } from "./Waterfall";
import type { SpectrumUpdate } from "./core";

const HEIGHT = 64;

function frame(
  magnitudes_db: number[],
  sync_detected = false,
): SpectrumUpdate {
  return {
    event_type: "spectrum_update",
    start_hz: 300,
    bin_hz: 20,
    magnitudes_db,
    sync_detected,
    peak_hz: null,
    peak_db: null,
  };
}

/** A quiet band: mostly noise, nothing standing out. */
const QUIET = Array.from({ length: 135 }, () => -84);

/** The same band with one very loud bin — a carrier, not a sync pulse. */
const LOUD = QUIET.map((db, i) => (i === 60 ? -20 : db));

function topPixel(data: Uint8ClampedArray): [number, number, number] {
  return [data[0], data[1], data[2]];
}

describe("a frame carrying sync", () => {
  it("is marked, and a merely loud frame is not", () => {
    const withSync = topPixel(paintColumn(frame(QUIET, true), HEIGHT));
    const justLoud = topPixel(paintColumn(frame(LOUD, false), HEIGHT));

    expect(withSync).not.toEqual(justLoud);
  });

  it("marks it in a colour energy never produces", () => {
    // The ramp runs dark-cool to bright-amber, so it can be cool *or*
    // bright but never both: the dark end is ink (#10161b, blue over red)
    // and the bright end is amber (red over blue). The sync mark is bright
    // and cool, which is a combination no signal level can reach -- that
    // is what makes it unmistakable rather than merely different.
    //
    // The first version of this test asserted "red always leads blue" and
    // failed on the ink end. The ramp was right; the claim was lazy.
    const coolAndBright = ([r, g, b]: [number, number, number]) =>
      b > r && (r + g + b) / 3 > 128;

    expect(coolAndBright(topPixel(paintColumn(frame(QUIET, true), HEIGHT)))).toBe(
      true,
    );

    // Every level the ramp can produce, from silence to a carrier that
    // pins the scale.
    for (let loudest = -84; loudest <= 0; loudest += 4) {
      const bins = QUIET.map((db, i) => (i === 60 ? loudest : db));
      for (let y = 0; y < HEIGHT; y += 1) {
        const column = paintColumn(frame(bins), HEIGHT);
        const pixel: [number, number, number] = [
          column[y * 4],
          column[y * 4 + 1],
          column[y * 4 + 2],
        ];
        expect(coolAndBright(pixel)).toBe(false);
      }
    }
  });

  it("spends only the top of the strip on it", () => {
    // The strip is 64px and its job is presence. A mark that took a
    // quarter of it would be reading as energy again.
    const marked = paintColumn(frame(QUIET, true), HEIGHT);
    const plain = paintColumn(frame(QUIET, false), HEIGHT);

    expect(SYNC_TICK_PX).toBeLessThanOrEqual(HEIGHT / 8);
    for (let y = SYNC_TICK_PX; y < HEIGHT; y += 1) {
      expect(marked.slice(y * 4, y * 4 + 4)).toEqual(
        plain.slice(y * 4, y * 4 + 4),
      );
    }
  });
});

describe("the column itself", () => {
  it("scales against the frame's own noise floor", () => {
    // The reason the strip is not a solid block. A SpyServer at gain 6
    // sits near -84 dBFS and a normalised recording near -9; an absolute
    // window paints one black and the other solid amber.
    const quiet = paintColumn(frame(QUIET.map((d, i) => (i === 60 ? -48 : d))), HEIGHT);
    const loud = paintColumn(
      frame(QUIET.map((d, i) => (i === 60 ? -48 : d)).map((d) => d + 75)),
      HEIGHT,
    );

    expect(Array.from(quiet)).toEqual(Array.from(loud));
  });

  it("puts low frequency at the bottom", () => {
    const bins = QUIET.map((db, i) => (i < 10 ? -20 : db));
    const column = paintColumn(frame(bins), HEIGHT);

    const brightness = (y: number) => column[y * 4] + column[y * 4 + 1] + column[y * 4 + 2];
    expect(brightness(HEIGHT - 1)).toBeGreaterThan(brightness(0));
  });

  it("survives a flat frame without dividing by zero", () => {
    // A muted input, or a source that has not started. Every bin equal
    // makes the span zero, and a NaN here paints the strip transparent.
    const column = paintColumn(frame(Array.from({ length: 135 }, () => -60)), HEIGHT);

    for (let i = 0; i < column.length; i += 1) {
      expect(Number.isNaN(column[i])).toBe(false);
    }
    expect(column[3]).toBe(255);
  });
});
