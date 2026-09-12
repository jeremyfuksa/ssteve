import { useEffect, useRef } from "react";
import type { ScanlineUpdate } from "./core";

/** The picture, painted as it arrives.
 *
 * Sized to the frame at a whole-number scale and claiming no space it is not
 * using for pixels (frontend-contract §20.4). Scale is what degrades on a
 * small window — not the waterfall, not the log.
 */
export function Canvas({
  scanline,
  frame,
  scale,
  completedUrl,
}: {
  scanline: ScanlineUpdate | null;
  frame: { width: number; height: number };
  scale: number;
  completedUrl: string | null;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const painted = useRef<string>("");

  // Clear when a new decode starts, identified by the frame size changing or
  // the canvas being handed a fresh session.
  useEffect(() => {
    const context = ref.current?.getContext("2d");
    if (!context) return;
    context.fillStyle = "#0b0f12";
    context.fillRect(0, 0, frame.width, frame.height);
    painted.current = "";
  }, [frame.width, frame.height]);

  // Rows straight from the event into the bitmap. No decode step between a
  // line arriving and it appearing (api/scanlines.py explains the integer
  // payload); putImageData is the reason the payload is shaped this way.
  useEffect(() => {
    if (!scanline?.rgb_rows?.length) return;
    const context = ref.current?.getContext("2d");
    if (!context) return;
    const first = scanline.first_row ?? 0;
    scanline.rgb_rows.forEach((row, index) => {
      const width = Math.floor(row.length / 3);
      if (!width) return;
      const data = new Uint8ClampedArray(width * 4);
      for (let x = 0; x < width; x += 1) {
        data[x * 4] = row[x * 3];
        data[x * 4 + 1] = row[x * 3 + 1];
        data[x * 4 + 2] = row[x * 3 + 2];
        data[x * 4 + 3] = 255;
      }
      context.putImageData(new ImageData(data, width, 1), 0, first + index);
    });
  }, [scanline]);

  // A finished decode shows the saved picture: the engine's output, slant
  // correction and all, rather than our accumulation of rows.
  useEffect(() => {
    if (!completedUrl || painted.current === completedUrl) return;
    const context = ref.current?.getContext("2d");
    if (!context) return;
    const image = new Image();
    image.onload = () => {
      context.drawImage(image, 0, 0, frame.width, frame.height);
      painted.current = completedUrl;
    };
    image.src = completedUrl;
  }, [completedUrl, frame.width, frame.height]);

  return (
    <div className="canvas-frame">
      <canvas
        ref={ref}
        width={frame.width}
        height={frame.height}
        style={{
          width: frame.width * scale,
          height: frame.height * scale,
          imageRendering: "pixelated",
        }}
        aria-label="Decoded picture"
      />
    </div>
  );
}
