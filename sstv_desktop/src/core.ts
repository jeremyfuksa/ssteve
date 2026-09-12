/** The core engine's REST + WebSocket surface.
 *
 * One module so the contract lives in one place. Shapes follow
 * docs/core/openapi.json and the WebSocket section of backend-spec.md; the
 * socket events are not in the OpenAPI export because they are not HTTP.
 */

/** Where the engine is.
 *
 * The shell starts the engine on a port it picks, so the window has to ask
 * rather than assume -- two copies of the app must not fight over 8000.
 * Outside Tauri (a browser, for layout work) the default is what a developer
 * running `uv run sstv-server` gets.
 */
const FALLBACK_ORIGIN = "http://127.0.0.1:8000";

let origin = FALLBACK_ORIGIN;

export async function locateEngine(): Promise<string> {
  // Ask first, decide afterwards. Checking for Tauri before asking cost the
  // real reason: the window reported a generic "can't reach it" while the
  // shell knew the engine had exited with status 1.
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    origin = await invoke<string>("engine_base_url");
  } catch {
    // Either a plain browser (layout work) or an app whose engine did not
    // start. Both fall back to the developer's port; the difference shows up
    // when a request fails, and `engineProblem` answers it then. Detecting
    // Tauri up front looked simpler and was wrong: isTauri() reported false
    // inside the real window.
  }
  return origin;
}

/** What the shell knows about why the engine is missing, if anything. */
export async function engineProblem(): Promise<string | null> {
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    return (await invoke<string | null>("engine_problem")) ?? null;
  } catch {
    return null;
  }
}

export const BASE = () => `${origin}/api/v1`;
const WS = () => `${origin.replace(/^http/, "ws")}/api/v1`;

export const BANDS = ["80m", "40m", "20m", "15m", "10m"] as const;
export type Band = (typeof BANDS)[number];

export type DecodeState =
  | "listening"
  | "vis_detected"
  | "decoding"
  | "completed"
  | "failed"
  | "stopped";

export interface Config {
  spyserver_host: string;
  spyserver_port: number;
  spyserver_frequency_hz: number;
  spyserver_gain: number | null;
  spyserver_my_stations: string[];
  image_library_path?: string;
  input_gain_override?: number | null;
  auto_squelch?: boolean;
  squelch_threshold_db?: number;
}

export interface ImageRow {
  id: string;
  url: string;
  thumbnail_url: string | null;
  mode: string | null;
  callsign: string | null;
  timestamp: string;
  snr_db: number | null;
  rsv_report: string | null;
  frequency_hz: number | null;
  width: number | null;
  height: number | null;
  source: string | null;
  receiver: string | null;
  heard_at: "my_station" | "remote" | null;
  fskid_detected: boolean | null;
  fskid_checksum_valid: boolean | null;
}

/** A failure the engine described. `detail` carries our own voice. */
export interface CoreErrorDetail {
  error?: string;
  message?: string;
  suggested_action?: string;
}

export class CoreError extends Error {
  suggestedAction?: string;
  code?: string;
  constructor(message: string, code?: string, suggestedAction?: string) {
    super(message);
    this.code = code;
    this.suggestedAction = suggestedAction;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE()}${path}`, {
      ...init,
      headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch (cause) {
    // The engine is a separate process. "Not running" is the first-run state,
    // not an exception, so it gets copy rather than a stack trace.
    throw new CoreError(
      "I can't reach the SSTeVe engine.",
      "ENGINE_UNREACHABLE",
      "Start it with `uv run sstv-server` from sstv_core, then try again.",
    );
  }
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail: CoreErrorDetail =
      (body && typeof body.detail === "object" ? body.detail : null) ?? {};
    throw new CoreError(
      detail.message ?? `${response.status} from ${path}`,
      detail.error,
      detail.suggested_action,
    );
  }
  return body as T;
}

export const getConfig = () => request<Config>("/config");

export const patchConfig = (updates: Partial<Config>) =>
  request<Config>("/config", { method: "PATCH", body: JSON.stringify(updates) });

export interface StartedSession {
  session_id: string;
  state: DecodeState;
  websocket_url: string;
}

export const startSpyServerDecode = (band: Band, timeoutSeconds: number) =>
  request<StartedSession>("/decode/start", {
    method: "POST",
    body: JSON.stringify({
      source: "spyserver",
      band,
      auto_detect: true,
      save_image: true,
      timeout_seconds: timeoutSeconds,
    }),
  });

export const startFileDecode = (filePath: string) =>
  request<StartedSession>("/decode/start", {
    method: "POST",
    body: JSON.stringify({
      source: "file",
      file_path: filePath,
      auto_detect: true,
      save_image: true,
      timeout_seconds: 3600,
    }),
  });

export const stopDecode = (sessionId: string) =>
  request<void>(`/decode/stop/${sessionId}`, { method: "POST" });

export const adjustDecode = (
  sessionId: string,
  changes: { input_gain?: number; auto_squelch?: boolean; squelch_threshold_db?: number },
) =>
  request<unknown>(`/decode/${sessionId}`, {
    method: "PATCH",
    body: JSON.stringify(changes),
  });

export const listImages = (limit = 40) =>
  request<{ images: ImageRow[]; total: number }>(`/images?limit=${limit}`);

/** An <img src> for a path the API gave us, on whichever port it is on. */
export const imageUrl = (path: string) => `${origin}${path}`;

/* ----------------------------- socket events ----------------------------- */

export interface SpectrumUpdate {
  event_type: "spectrum_update";
  start_hz: number;
  bin_hz: number;
  magnitudes_db: number[];
  sync_detected: boolean;
  peak_hz: number | null;
  peak_db: number | null;
}

export interface AudioLevels {
  event_type: "audio_levels";
  left_db: number;
  peak_db: number;
  is_clipping: boolean;
}

export interface VISDetected {
  event_type: "vis_detected";
  mode: string;
  confidence: number;
}

export interface ScanlineUpdate {
  event_type: "scanline_update";
  scanline_number: number;
  total_scanlines: number;
  progress_percent: number;
  signal_quality: number;
  snr_db: number | null;
  /** Each row is flat [r,g,b,...]; width is row.length / 3 (api/scanlines.py). */
  rgb_rows: number[][] | null;
  first_row: number | null;
}

export interface DecodeComplete {
  event_type: "decode_complete";
  image_id: string | null;
  mode: string | null;
  duration_seconds: number;
  rsv_report: string | null;
  fskid_detected: boolean | null;
  fskid_checksum_valid: boolean | null;
}

export interface CoreErrorEvent {
  event_type: "error";
  error_code: string;
  message: string;
  recoverable: boolean;
  suggested_action: string | null;
}

export type SessionEvent =
  | AudioLevels
  | VISDetected
  | ScanlineUpdate
  | DecodeComplete
  | CoreErrorEvent
  | { event_type: string };

/** Subscribe to one decode session. Returns a closer. */
export function watchSession(
  sessionId: string,
  onEvent: (event: SessionEvent) => void,
): () => void {
  return reconnecting(`${WS()}/ws/decode/${sessionId}`, onEvent);
}

/** Subscribe to the app channel, which carries the waterfall. */
export function watchApp(onEvent: (event: SpectrumUpdate | { event_type: string }) => void) {
  return reconnecting(`${WS()}/ws`, onEvent);
}

function reconnecting(url: string, onEvent: (event: any) => void): () => void {
  let socket: WebSocket | null = null;
  let timer: number | undefined;
  let closed = false;

  const open = () => {
    if (closed) return;
    socket = new WebSocket(url);
    socket.onmessage = (message) => {
      try {
        onEvent(JSON.parse(message.data));
      } catch {
        /* A malformed frame is not worth taking the session down for. */
      }
    };
    // Reconnect rather than go quiet: a socket that dropped looks exactly
    // like a band with nothing on it, which is the confusion this whole
    // product tries to avoid.
    socket.onclose = () => {
      if (!closed) timer = window.setTimeout(open, 1000);
    };
  };
  open();

  return () => {
    closed = true;
    window.clearTimeout(timer);
    socket?.close();
  };
}
