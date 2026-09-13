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

/** The SSTV calling frequency for each band, in Hz.
 *
 *  A copy of `sdr/bands.py`'s table, and the only one in this app. It is
 *  here so the band buttons can be *saved* -- the engine resolves a band
 *  name on `decode/start`, but `config` stores a frequency, so persisting
 *  the chosen band means knowing which frequency it is. Adding a band
 *  means editing both, which `bandFor` makes loud by returning undefined
 *  rather than guessing.
 */
export const BAND_FREQUENCIES: Record<Band, number> = {
  "80m": 3_845_000,
  "40m": 7_171_000,
  "20m": 14_230_000,
  "15m": 21_340_000,
  "10m": 28_680_000,
};

/** Which band a saved frequency belongs to, if it is one of the presets.
 *
 *  A frequency typed in by hand need not be a band, and saying so is
 *  better than rounding it to the nearest button.
 */
export function bandFor(frequencyHz: number): Band | undefined {
  return BANDS.find((band) => BAND_FREQUENCIES[band] === frequencyHz);
}

/** The band a frequency sits closest to.
 *
 *  Only for asking about propagation, which is reported per band and has
 *  no notion of an exact frequency. Tuning uses the frequency itself.
 */
export function nearestBand(frequencyHz: number): Band {
  return BANDS.reduce((closest, band) =>
    Math.abs(BAND_FREQUENCIES[band] - frequencyHz) <
    Math.abs(BAND_FREQUENCIES[closest] - frequencyHz)
      ? band
      : closest,
  );
}

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
  /** How long a silent stream may go before the session gives up on it. */
  spyserver_stall_timeout_sec?: number;
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
  } catch {
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

/** Listen on a SpyServer.
 *
 *  A null band means "the frequency that is saved": the engine falls back
 *  to `spyserver_frequency_hz` when given neither a band nor a frequency,
 *  which is how an operator who typed 14.233 gets 14.233 rather than the
 *  20m preset they did not ask for.
 */
export const startSpyServerDecode = (band: Band | null, timeoutSeconds: number) =>
  request<StartedSession>("/decode/start", {
    method: "POST",
    body: JSON.stringify({
      source: "spyserver",
      ...(band ? { band } : {}),
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

/** What the engine says a session is doing.
 *
 * The authority when the socket and the window disagree. The socket is a
 * live feed, so a dropped connection loses whatever arrived while it was
 * down -- including the `decode_complete` or `error` that ended the
 * session. Only 10 of the 17 fields the engine returns are named here; the
 * rest are not yet rendered anywhere.
 */
export interface DecodeStatus {
  session_id: string;
  state: DecodeState;
  mode: string | null;
  mode_confidence: number | null;
  image_id: string | null;
  error: string | null;
  progress_percent: number;
  scanlines_received: number;
  total_scanlines: number | null;
  vis_detected: boolean;
}

export const decodeStatus = (sessionId: string) =>
  request<DecodeStatus>(`/decode/status/${sessionId}`);

export interface DecodeAdjustment {
  input_gain?: number;
  auto_squelch?: boolean;
  squelch_threshold_db?: number;
}

/** What the decode is using now, after the change.
 *
 *  `applied` is read back from the running decode rather than echoed from
 *  the request, so it is what to display -- not the value that was asked
 *  for.
 */
export interface DecodeAdjusted {
  session_id: string;
  applied: DecodeAdjustment;
}

export const adjustDecode = (sessionId: string, changes: DecodeAdjustment) =>
  request<DecodeAdjusted>(`/decode/${sessionId}`, {
    method: "PATCH",
    body: JSON.stringify(changes),
  });

export interface Propagation {
  band: string;
  state: "OPEN" | "CLOSED" | "STORM" | "UNKNOWN";
  condition: string;
  time_of_day: string;
  /** The sentence a fault report needs, written by the engine. */
  explanation: string;
  solar_flux: string;
  k_index: string;
  a_index: string;
  sunspots: string;
  xray: string;
  updated: string;
  source_errors: string[];
}

/** Whether the band should be carrying signal.
 *
 * The only answer that cannot fail in the same direction as our own gain,
 * antenna or demodulator -- which is what makes it worth asking when a
 * capture reads dead (PRODUCT.md requirement 13). A 503 means the sources
 * were unreachable, never that conditions are poor, and the caller must
 * render that difference.
 */
export const getPropagation = (band: Band) =>
  request<Propagation>(`/propagation?band=${band}`);

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

/** Transmit progress. Nothing renders it yet -- v0.1 is receive-only --
 *  but it arrives on the session socket, so it is named rather than
 *  silently dropped. */
export interface TxProgress {
  event_type: "tx_progress";
  progress_percent: number;
  scanline_number: number;
  total_scanlines: number;
}

export interface TransmitComplete {
  event_type: "transmit_complete";
  tx_id: string;
  duration_seconds: number;
}

/** An image entered, changed or left the library on disk.
 *
 *  `broadcast_library_event` sends this to the app channel *and* to every
 *  session connection (websocket_manager.py:250-272), so it arrives on
 *  both.
 */
export interface LibraryUpdated {
  event_type: "library_updated";
  action: "created" | "modified" | "deleted";
  image_id: string | null;
  filepath: string;
}

export interface DeviceChanged {
  event_type: "device_changed";
  added: string[];
  removed: string[];
  total: number;
}

export interface MonitorState {
  event_type: "monitor_state";
  monitoring: boolean;
  device_id: string | null;
}

/** An event type this build does not know.
 *
 *  Not the same as one it chooses to ignore. A newer engine may send
 *  something this window has never heard of, and the difference between
 *  "not handled yet" and "handled by doing nothing" is the difference
 *  between a gap and a decision.
 */
export interface UnknownEvent {
  event_type: "__unknown__";
  raw: { event_type?: string };
}

/** Everything the session socket can deliver.
 *
 *  The seven the engine broadcasts to a session, plus library_updated,
 *  which goes to both sockets. Listing them is the point: the switch that
 *  consumes this is checked for exhaustiveness, so adding an event to the
 *  engine and not to the window becomes a lint error rather than a silent
 *  drop. Seven of the twelve were being dropped before this (#145).
 */
export type SessionEvent =
  | AudioLevels
  | VISDetected
  | ScanlineUpdate
  | DecodeComplete
  | CoreErrorEvent
  | TxProgress
  | TransmitComplete
  | LibraryUpdated
  | UnknownEvent;

/** Everything the app channel can deliver. */
export type AppEvent =
  | SpectrumUpdate
  | DeviceChanged
  | MonitorState
  | LibraryUpdated
  | UnknownEvent;

const SESSION_EVENTS = new Set([
  "audio_levels",
  "vis_detected",
  "scanline_update",
  "decode_complete",
  "error",
  "tx_progress",
  "transmit_complete",
  "library_updated",
]);

const APP_EVENTS = new Set([
  "spectrum_update",
  "device_changed",
  "monitor_state",
  "library_updated",
]);

/** Give an unrecognised frame a name the type system can see.
 *
 *  Without this the union needed a `{ event_type: string }` member, which
 *  matched everything and made exhaustiveness checking impossible: the
 *  compiler could not tell a handled event from an unhandled one, so the
 *  switch with no default type-checked perfectly while dropping seven
 *  event types.
 */
function label<T>(known: Set<string>, frame: { event_type?: string }): T {
  return (known.has(frame.event_type ?? "")
    ? frame
    : { event_type: "__unknown__", raw: frame }) as T;
}

/** Subscribe to one decode session. Returns a closer.
 *
 * `onOpen` fires on every connect, reconnects included, because the socket
 * is a live feed and not a log: anything the engine sent while it was down
 * is gone. The caller uses it to re-read `decodeStatus` and find out what
 * it missed.
 */
export function watchSession(
  sessionId: string,
  onEvent: (event: SessionEvent) => void,
  onOpen?: () => void,
): () => void {
  return reconnecting(
    `${WS()}/ws/decode/${sessionId}`,
    (frame) => onEvent(label<SessionEvent>(SESSION_EVENTS, frame)),
    onOpen,
  );
}

/** Subscribe to the app channel, which carries the waterfall. */
/** Subscribe to the app channel, which carries the waterfall.
 *
 *  `onOpen` is the dependable "the engine is reachable again" signal. The
 *  session socket's is not: the engine closes that one *before* accepting
 *  when it does not know the session (routes/websocket.py), so the browser
 *  reports a failed handshake and never fires `open` -- in exactly the
 *  case the caller most needs to hear about, a restarted engine that has
 *  lost the session. This channel accepts unconditionally.
 */
export function watchApp(onEvent: (event: AppEvent) => void, onOpen?: () => void) {
  return reconnecting(
    `${WS()}/ws`,
    (frame) => onEvent(label<AppEvent>(APP_EVENTS, frame)),
    onOpen,
  );
}

function reconnecting(
  url: string,
  onEvent: (frame: { event_type?: string }) => void,
  onOpen?: () => void,
): () => void {
  let socket: WebSocket | null = null;
  let timer: number | undefined;
  let closed = false;

  const open = () => {
    if (closed) return;
    socket = new WebSocket(url);
    socket.onopen = () => onOpen?.();
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
