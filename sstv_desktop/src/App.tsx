import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BANDS,
  CoreError,
  adjustDecode,
  getConfig,
  imageUrl,
  listImages,
  engineProblem,
  locateEngine,
  patchConfig,
  startFileDecode,
  startSpyServerDecode,
  stopDecode,
  watchApp,
  watchSession,
  type Band,
  type Config,
  type ImageRow,
  type ScanlineUpdate,
  type SpectrumUpdate,
} from "./core";
import { Canvas } from "./Canvas";
import { Waterfall } from "./Waterfall";
import "./theme.css";
import "./layout.css";

/** What the operator is told is happening. One vocabulary, from PRODUCT.md:
 *  Listen / Listening / Decoding / Decode Complete. */
type Posture =
  | { kind: "idle" }
  | { kind: "listening"; since: number }
  | { kind: "decoding"; mode: string; confidence: number }
  | { kind: "complete"; mode: string | null; rsv: string | null; fskid: string | null }
  | { kind: "failed"; message: string; action: string | null; code: string }
  // Hearing nothing is the band's normal state, not a fault. It gets its
  // own posture so it does not read in alarm red all day.
  | { kind: "nothing"; message: string; action: string | null };

/** Times are shown in UTC, which is what amateur radio logs in — and what the
 *  engine stores. Marked as such, because a bare "2:14" that is neither the
 *  operator's clock nor obviously not it is the worst of both. */
function heardAt(timestamp: string): string {
  const at = new Date(timestamp);
  if (Number.isNaN(at.getTime())) return "unknown time";
  return `${at.toISOString().slice(11, 19)}Z`;
}

const DEFAULT_FRAME = { width: 320, height: 256 };

export default function App() {
  const [config, setConfig] = useState<Config | null>(null);
  const [band, setBand] = useState<Band>("20m");
  const [session, setSession] = useState<string | null>(null);
  const [posture, setPosture] = useState<Posture>({ kind: "idle" });
  const [spectrum, setSpectrum] = useState<SpectrumUpdate | null>(null);
  const [levelDb, setLevelDb] = useState<number | null>(null);
  const [scanline, setScanline] = useState<ScanlineUpdate | null>(null);
  const [completedUrl, setCompletedUrl] = useState<string | null>(null);
  const [images, setImages] = useState<ImageRow[]>([]);
  const [engineError, setEngineError] = useState<string | null>(null);
  const [engineAction, setEngineAction] = useState<string | null>(null);
  const [gain, setGain] = useState(1);
  const [squelch, setSquelch] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const closeSession = useRef<(() => void) | null>(null);

  const refreshImages = useCallback(async () => {
    try {
      const { images: rows } = await listImages(40);
      setImages(rows);
    } catch {
      /* The log is not worth an error banner; the engine state already shows. */
    }
  }, []);

  const [starting, setStarting] = useState(true);

  useEffect(() => {
    let stopWatching: (() => void) | undefined;
    // Find the engine first: the shell starts it on a port it picks, so
    // nothing can be fetched until we know where it is.
    locateEngine()
      .then(async () => {
        const loaded = await getConfig();
        setConfig(loaded);
        setEngineError(null);
        if (loaded.input_gain_override) setGain(loaded.input_gain_override);
        await refreshImages();
        stopWatching = watchApp((event) => {
          if (event.event_type === "spectrum_update") setSpectrum(event as SpectrumUpdate);
        });
      })
      .catch(async (error: CoreError) => {
        // The shell may know more than "I can't reach it" -- that the engine
        // exited with a status, or is missing from the build.
        const known = await engineProblem();
        setEngineError(known ? `The SSTeVe engine didn't start: ${known}.` : error.message);
        setEngineAction(
          known
            ? "Quit and reopen SSTeVe. If it keeps happening, this build's engine is broken."
            : (error.suggestedAction ?? null),
        );
      })
      .finally(() => setStarting(false));
    return () => stopWatching?.();
  }, [refreshImages]);

  /** Start a decode and follow it. The starter decides where the audio comes
   *  from; everything downstream is identical, which is the point of the
   *  source seam in the engine. */
  const begin = async (start: () => Promise<{ session_id: string }>) => {
    setScanline(null);
    setCompletedUrl(null);
    try {
      const started = await start();
      setSession(started.session_id);
      setPosture({ kind: "listening", since: Date.now() });
      setEngineError(null);
      closeSession.current = watchSession(started.session_id, (event) => {
        switch (event.event_type) {
          case "audio_levels":
            setLevelDb((event as any).left_db);
            break;
          case "vis_detected":
            setPosture({
              kind: "decoding",
              mode: (event as any).mode,
              confidence: (event as any).confidence,
            });
            break;
          case "scanline_update":
            setScanline(event as ScanlineUpdate);
            break;
          case "decode_complete": {
            const done = event as any;
            setPosture({
              kind: "complete",
              mode: done.mode,
              rsv: done.rsv_report,
              fskid: done.fskid_detected
                ? done.fskid_checksum_valid
                  ? "verified"
                  : "unverified"
                : null,
            });
            if (done.image_id) setCompletedUrl(imageUrl(`/api/v1/images/${done.image_id}/file`));
            refreshImages();
            break;
          }
          case "error": {
            const failure = event as any;
            setPosture(
              failure.error_code === "NOTHING_HEARD"
                ? {
                    kind: "nothing",
                    message: failure.message,
                    action: failure.suggested_action,
                  }
                : {
                    kind: "failed",
                    message: failure.message,
                    action: failure.suggested_action,
                    code: failure.error_code,
                  },
            );
            break;
          }
        }
      });
    } catch (error) {
      const failure = error as CoreError;
      setPosture({
        kind: "failed",
        message: failure.message,
        action: failure.suggestedAction ?? null,
        code: failure.code ?? "UNKNOWN",
      });
    }
  };

  const listen = () => begin(() => startSpyServerDecode(band, 3600));
  const replay = (filePath: string) => begin(() => startFileDecode(filePath));

  const stop = async () => {
    if (session) await stopDecode(session).catch(() => undefined);
    closeSession.current?.();
    closeSession.current = null;
    setSession(null);
    setPosture({ kind: "idle" });
    setLevelDb(null);
  };

  const live = posture.kind === "listening" || posture.kind === "decoding";

  // Canvas scale degrades before anything else. 2x at a comfortable window,
  // 1.5x at the field floor (moscow.md).
  const [scale, setScale] = useState(2);
  useEffect(() => {
    // Measured against a populated log (2026-09-12): 2x needs ~860px of
    // height, 1.5x fits the 1280x720 field floor with a whole filmstrip card
    // under it, and below ~740px only 1x leaves the log enough room to show
    // a picture with its time, callsign and provenance. The canvas is what
    // gives way -- the log and the presence strip hold.
    const measure = () =>
      setScale(window.innerHeight >= 860 ? 2 : window.innerHeight >= 740 ? 1.5 : 1);
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);

  const frame = useMemo(() => {
    const total = scanline?.total_scanlines;
    const width = scanline?.rgb_rows?.[0] ? scanline.rgb_rows[0].length / 3 : DEFAULT_FRAME.width;
    return { width, height: total && total > 1 ? total : DEFAULT_FRAME.height };
  }, [scanline]);

  const pushGain = async (value: number) => {
    setGain(value);
    if (session) await adjustDecode(session, { input_gain: value }).catch(() => undefined);
  };

  const pushSquelch = async (value: boolean) => {
    setSquelch(value);
    if (session) await adjustDecode(session, { auto_squelch: value }).catch(() => undefined);
  };

  const host = config?.spyserver_host ?? "";
  const mine = (config?.spyserver_my_stations ?? []).some(
    (entry) => entry.toLowerCase().split(":")[0] === host.toLowerCase(),
  );

  return (
    <div className="shell">
      <header className="bar">
        <div className="receiver">
          <span className={`lamp ${live ? "on" : ""}`} aria-hidden />
          <span className="mono">{host || "no receiver saved"}</span>
          {host && <span className="tag">{mine ? "my station" : "remote"}</span>}
        </div>
        <div className="bands" role="group" aria-label="Band">
          {BANDS.map((option) => (
            <button
              key={option}
              className={option === band ? "band on" : "band"}
              onClick={() => setBand(option)}
              disabled={live}
            >
              {option}
            </button>
          ))}
        </div>
        {live ? (
          <button className="stop" onClick={stop}>
            Stop
          </button>
        ) : (
          <button className="primary" onClick={listen} disabled={!host}>
            Listen
          </button>
        )}
        <button onClick={() => setSettingsOpen(true)}>Settings</button>
      </header>

      <section className="instrument">
        <Canvas scanline={scanline} frame={frame} scale={scale} completedUrl={completedUrl} />
        <Waterfall frame={spectrum} />
        <div className="controls">
          <label className="control">
            Gain
            <input
              type="range"
              min={0}
              max={2}
              step={0.05}
              value={gain}
              onChange={(event) => pushGain(Number(event.target.value))}
            />
            <span className="mono value">{gain.toFixed(2)}×</span>
          </label>
          <label className="control checkbox">
            <input
              type="checkbox"
              checked={squelch}
              onChange={(event) => pushSquelch(event.target.checked)}
            />
            Squelch
          </label>
          <span className="spacer" />
          <Status posture={posture} levelDb={levelDb} scanline={scanline} spectrum={spectrum} />
        </div>
      </section>

      <section className="log" aria-label="Log">
        {starting && !engineError && <p className="empty">Starting the engine…</p>}
        {engineError && (
          <p className="engine-down">
            {engineError}
            {engineAction && <span className="muted"> {engineAction}</span>}
          </p>
        )}
        {!starting && !engineError && images.length === 0 && (
          <p className="empty">Nothing decoded yet. The band is quiet most of the time.</p>
        )}
        <div className="rows">
          {images.map((row) => (
            <figure key={row.id} className="row">
              <img
                src={imageUrl(row.thumbnail_url ?? row.url)}
                alt={`${row.mode ?? "Unknown mode"} decoded at ${heardAt(row.timestamp)}`}
              />
              <figcaption>
                {/* Two lines, fixed: what and when, then who and where.
                    At the field floor the log gets ~155px, so a third line
                    falls off the bottom. */}
                <span className="line">
                  <span className="mono">{heardAt(row.timestamp)}</span>
                  <span>{row.mode ?? "unknown"}</span>
                  {row.rsv_report && <span className="mono rsv">{row.rsv_report}</span>}
                </span>
                <span className="line">
                  {row.callsign ? (
                    <span className="call">{row.callsign}</span>
                  ) : (
                    <span className="call unknown">no callsign</span>
                  )}
                  <span
                    className={row.heard_at === "remote" ? "where remote" : "where"}
                    title={
                      row.heard_at === "remote"
                        ? `Heard at ${row.receiver ?? "another receiver"} — a remote reception, never exported as a contact`
                        : row.heard_at === "my_station"
                          ? "Heard at my station"
                          : row.source === "file"
                            ? "Decoded from a recording"
                            : "Source unknown"
                    }
                  >
                    {row.heard_at === "remote"
                      ? "remote"
                      : row.heard_at === "my_station"
                        ? "my station"
                        : row.source === "file"
                          ? "recording"
                          : "unknown"}
                  </span>
                </span>
              </figcaption>
            </figure>
          ))}
        </div>
      </section>

      {settingsOpen && config && (
        <Settings
          config={config}
          onReplay={(path) => {
            setSettingsOpen(false);
            replay(path);
          }}
          onClose={() => setSettingsOpen(false)}
          onSaved={(saved) => {
            setConfig(saved);
            setSettingsOpen(false);
          }}
        />
      )}
    </div>
  );
}

function Status({
  posture,
  levelDb,
  scanline,
  spectrum,
}: {
  posture: Posture;
  levelDb: number | null;
  scanline: ScanlineUpdate | null;
  spectrum: SpectrumUpdate | null;
}) {
  if (posture.kind === "nothing") {
    return (
      <p className="status heard-nothing">
        <span>{posture.message}</span>
        {posture.action && <span className="muted">{posture.action}</span>}
      </p>
    );
  }
  if (posture.kind === "failed") {
    return (
      <p className="status failed">
        <span>{posture.message}</span>
        {posture.action && <span className="muted">{posture.action}</span>}
      </p>
    );
  }
  if (posture.kind === "decoding") {
    const percent = scanline ? Math.round(scanline.progress_percent) : 0;
    return (
      <p className="status">
        Decoding {posture.mode}
        <span className="mono">
          {percent}% · line {scanline?.scanline_number ?? 0}/{scanline?.total_scanlines ?? "?"}
          {scanline?.snr_db != null && ` · ${scanline.snr_db.toFixed(1)} dB`}
        </span>
      </p>
    );
  }
  if (posture.kind === "complete") {
    return (
      <p className="status">
        Decode complete
        <span className="mono">
          {[posture.mode, posture.rsv, posture.fskid && `FSKID ${posture.fskid}`]
            .filter(Boolean)
            .join(" · ")}
        </span>
      </p>
    );
  }
  if (posture.kind === "listening") {
    // "Deaf" and "quiet band" are different facts and the level is what
    // separates them — the distinction that cost the first live session its
    // first decode (#90).
    // -66 dBFS is the engine's own deaf threshold (cli DEAF_RMS 0.0005): below
    // it, the receiver is not hearing the band rather than the band being
    // quiet. Say which, and say what to turn.
    const deaf = levelDb != null && levelDb < -66;
    return (
      <p className="status">
        Listening
        <span className="mono">
          {levelDb == null ? "…" : `${levelDb.toFixed(0)} dB`}
          {spectrum?.sync_detected && " · sync"}
        </span>
        {deaf && <span className="muted">barely hearing anything — try a higher receiver gain</span>}
      </p>
    );
  }
  return <p className="status muted">Idle</p>;
}

function Settings({
  config,
  onClose,
  onSaved,
  onReplay,
}: {
  config: Config;
  onClose: () => void;
  onSaved: (config: Config) => void;
  onReplay: (filePath: string) => void;
}) {
  const [host, setHost] = useState(config.spyserver_host);
  const [port, setPort] = useState(config.spyserver_port);
  const [gainIndex, setGainIndex] = useState<string>(
    config.spyserver_gain == null ? "" : String(config.spyserver_gain),
  );
  const key = `${host.trim().toLowerCase()}:${port}`;
  const [mine, setMine] = useState(
    (config.spyserver_my_stations ?? []).some((entry) => entry.toLowerCase() === key),
  );
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [recording, setRecording] = useState("");

  const save = async () => {
    setSaving(true);
    setProblem(null);
    const others = (config.spyserver_my_stations ?? []).filter(
      (entry) => entry.toLowerCase() !== key,
    );
    try {
      onSaved(
        await patchConfig({
          spyserver_host: host.trim(),
          spyserver_port: port,
          spyserver_gain: gainIndex === "" ? null : Number(gainIndex),
          spyserver_my_stations: mine ? [...others, key] : others,
        }),
      );
    } catch (error) {
      setProblem((error as CoreError).message);
      setSaving(false);
    }
  };

  return (
    <div className="scrim" onClick={onClose}>
      <div className="panel" onClick={(event) => event.stopPropagation()}>
        <h2>Receiver</h2>
        <label>
          SpyServer host
          <input value={host} onChange={(event) => setHost(event.target.value)} placeholder="airspy.local" />
        </label>
        <label>
          Port
          <input
            type="number"
            value={port}
            onChange={(event) => setPort(Number(event.target.value))}
          />
        </label>
        <label>
          Receiver gain
          <input
            type="number"
            min={0}
            max={63}
            value={gainIndex}
            placeholder="automatic"
            onChange={(event) => setGainIndex(event.target.value)}
          />
        </label>
        <label className="checkbox">
          <input type="checkbox" checked={mine} onChange={(event) => setMine(event.target.checked)} />
          This receiver is my station
        </label>
        <p className="note">
          Pictures heard at someone else's receiver are logged as remote receptions and never
          exported as contacts.
        </p>
        {problem && <p className="failed">{problem}</p>}
        <h2>Replay a recording</h2>
        <label>
          Path on this machine
          <input
            value={recording}
            onChange={(event) => setRecording(event.target.value)}
            placeholder="/path/to/capture.wav"
          />
        </label>
        <p className="note">
          Plays a recording through the live decoder at the speed it was recorded — the band is
          silent most of the time, and this is how you see a decode on demand.
        </p>
        <div className="actions">
          <button onClick={() => onReplay(recording.trim())} disabled={!recording.trim()}>
            Replay
          </button>
        </div>

        <div className="actions">
          <button onClick={onClose}>Cancel</button>
          <button className="primary" onClick={save} disabled={saving || !host.trim()}>
            {saving ? "Saving…" : "Save receiver"}
          </button>
        </div>
      </div>
    </div>
  );
}
