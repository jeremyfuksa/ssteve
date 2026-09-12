import { useEffect, useRef } from "react";
import type { SpectrumUpdate } from "./core";

/** The presence strip.
 *
 * A presence display, not a tuning instrument (moscow.md): everything is
 * automatic, so nobody reads a number off it. Its job is visual proof that
 * reception is happening, and it doubles as the silence display — the same
 * feed shows the live noise floor for the 97.4% of the time the band is quiet.
 *
 * Scrolls right to left, newest column at the right edge, which is how every
 * waterfall an operator has seen behaves.
 */
export function Waterfall({ frame }: { frame: SpectrumUpdate | null }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const last = useRef<SpectrumUpdate | null>(null);

  useEffect(() => {
    if (!frame || frame === last.current) return;
    last.current = frame;
    const canvas = ref.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;

    // Shift the existing image one column left, then draw the new column.
    context.drawImage(canvas, -1, 0);
    const height = canvas.height;
    const x = canvas.width - 1;
    const bins = frame.magnitudes_db;
    const column = context.createImageData(1, height);

    // Scale against this frame's own noise floor rather than absolute dBFS.
    // Absolute thresholds cannot work here: a SpyServer at gain 6 delivers a
    // quiet band around -84 dBFS while a normalised recording sits near -9,
    // and a fixed window paints one of them black and the other solid amber
    // (seen: the first replay through this strip was a solid block).
    // The median is the noise floor because the band is mostly noise; 36 dB
    // above it covers a strong carrier without clipping every sync pulse.
    const sorted = [...bins].sort((a, b) => a - b);
    const floorDb = sorted[Math.floor(sorted.length / 2)];
    const spanDb = Math.max(18, Math.min(48, sorted[sorted.length - 1] - floorDb));

    for (let y = 0; y < height; y += 1) {
      // Low frequency at the bottom, as on any waterfall.
      const bin = Math.min(
        bins.length - 1,
        Math.floor(((height - 1 - y) / height) * bins.length),
      );
      const t = Math.max(0, Math.min(1, (bins[bin] - floorDb) / spanDb));
      // Ink -> amber ramp. One hue, so brightness carries the information and
      // a false-colour rainbow does not imply precision the strip lacks.
      const [r, g, b] = ramp(t);
      const offset = y * 4;
      column.data[offset] = r;
      column.data[offset + 1] = g;
      column.data[offset + 2] = b;
      column.data[offset + 3] = 255;
    }
    context.putImageData(column, x, 0);
  }, [frame]);

  return (
    <canvas
      ref={ref}
      width={900}
      height={64}
      className="waterfall"
      aria-label="Spectrum, 300 to 3000 hertz"
    />
  );
}

function ramp(t: number): [number, number, number] {
  // #10161b -> #f2b63c through a warm midtone, so sync pulses read as bright
  // lines rather than a colour change.
  const stops: Array<[number, [number, number, number]]> = [
    [0, [16, 22, 27]],
    [0.45, [54, 58, 58]],
    [0.75, [150, 108, 52]],
    [1, [242, 182, 60]],
  ];
  for (let i = 1; i < stops.length; i += 1) {
    const [to, high] = stops[i];
    const [from, low] = stops[i - 1];
    if (t <= to) {
      const k = (t - from) / (to - from);
      return [
        Math.round(low[0] + (high[0] - low[0]) * k),
        Math.round(low[1] + (high[1] - low[1]) * k),
        Math.round(low[2] + (high[2] - low[2]) * k),
      ];
    }
  }
  return stops[stops.length - 1][1];
}
