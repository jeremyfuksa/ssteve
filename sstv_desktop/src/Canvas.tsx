import { useEffect, useRef } from "react";
import type { ScanlineUpdate } from "./core";

/** The picture, painted as it arrives.
 *
 * Sized to the frame and claiming no space it is not using for pixels
 * (frontend-contract §20.4). Scale is what degrades on a small window —
 * not the waterfall, not the log.
 */
export function Canvas({
  scanline,
  frame,
  scale,
  completedUrl,
  failed,
}: {
  scanline: ScanlineUpdate | null;
  frame: { width: number; height: number };
  scale: number;
  completedUrl: string | null;
  /** The decode stopped before the picture did. */
  failed: boolean;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const painted = useRef<string>("");
  // How far down the picture got. The rows above it are real signal and
  // worth keeping; everything below never arrived.
  const reached = useRef<number>(0);

  // Clear when a new decode starts, identified by the frame size changing or
  // the canvas being handed a fresh session.
  useEffect(() => {
    const context = ref.current?.getContext("2d");
    if (!context) return;
    context.fillStyle = "#0b0f12";
    context.fillRect(0, 0, frame.width, frame.height);
    painted.current = "";
    reached.current = 0;
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
      reached.current = Math.max(reached.current, first + index + 1);
    });
  }, [scanline]);

  // A decode that stopped early must not read as a picture that simply had
  // a dark bottom. The rows that arrived stay — on a weak signal they are
  // often the only thing carrying a callsign — and the region that never
  // arrived is hatched, which is a texture no SSTV frame produces, so the
  // boundary between "received" and "never sent" is unmistakable.
  useEffect(() => {
    const context = ref.current?.getContext("2d");
    if (!context || !failed) return;
    const from = reached.current;
    if (from >= frame.height) return;

    context.fillStyle = "#0b0f12";
    context.fillRect(0, from, frame.width, frame.height - from);
    context.strokeStyle = "rgba(226, 89, 59, 0.5)";
    context.lineWidth = 1;
    for (let x = -frame.height; x < frame.width; x += 8) {
      context.beginPath();
      context.moveTo(x, from);
      context.lineTo(x + (frame.height - from), frame.height);
      context.stroke();
    }

    // The line where the signal stopped, in the colour the rest of the
    // window uses for a stream that died rather than for a weak one.
    context.fillStyle = "#e2593b";
    context.fillRect(0, from, frame.width, 1);
  }, [failed, frame.width, frame.height, scanline]);

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
