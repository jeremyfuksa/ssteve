import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BAND_FREQUENCIES,
  BANDS,
  CoreError,
  adjustDecode,
  type DecodeAdjustment,
  bandFor,
  nearestBand,
  getConfig,
  getPropagation,
  imageUrl,
  listImages,
  engineProblem,
  locateEngine,
  patchConfig,
  startFileDecode,
  startSpyServerDecode,
  decodeStatus,
  stopDecode,
  watchApp,
  watchSession,
  type Band,
  type Config,
  type ImageRow,
  type Propagation,
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
  | {
      kind: "complete";
      mode: string | null;
      rsv: string | null;
      fskid: string | null;
      /** For looking up where it was heard; the event does not carry that. */
      imageId: string | null;
    }
  // `retryStop` means the engine may still hold the session: a stop that
  // did not take leaves the radio busy, so the control has to stay Stop.
  | {
      kind: "failed";
      message: string;
      action: string | null;
      code: string;
      retryStop?: true;
    }
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
  // Null means the operator saved a frequency that is not one of the five
  // presets -- 14.233, say. The buttons then show none selected, because
  // none of them is what the radio is on.
  const [band, setBand] = useState<Band | null>("20m");
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
  // Why the last adjustment did not take, when it did not.
  const [adjustment, setAdjustment] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  // The picture being looked at full size, if any.
  const [viewing, setViewing] = useState<ImageRow | null>(null);
  const [propagation, setPropagation] = useState<Propagation | null>(null);
  const [propagationProblem, setPropagationProblem] = useState<string | null>(null);
  const [indicesOpen, setIndicesOpen] = useState(false);
  const closeSession = useRef<(() => void) | null>(null);

  const refreshImages = useCallback(async () => {
    try {
      const { images: rows } = await listImages(40);
      setImages(rows);
    } catch {
      /* The log is not worth an error banner; the engine state already shows. */
    }
  }, []);

  // Bumped every time the app channel connects, including reconnects.
  // This is the dependable "the engine is back" signal: the session socket
  // is closed *before* being accepted when the engine does not know the
  // session, so the browser sees a refused handshake and never fires open
  // -- in exactly the case that matters, an engine that restarted and lost
  // the decode.
  const [engineReachedAt, setEngineReachedAt] = useState(0);
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
        // The band survives a restart now. It used to be component state
        // only, so the app reopened on 20m whatever you had been listening
        // to -- and "listening is one click from then on" (#150) is not
        // true if the first click is putting the band back.
        setBand(bandFor(loaded.spyserver_frequency_hz) ?? null);
        // Squelch was hard-coded off, which happened to match what the
        // engine does for a SpyServer and silently disagreed with it for
        // anything else. Read the saved setting like the gain beside it.
        setSquelch(loaded.auto_squelch ?? false);
        await refreshImages();
        stopWatching = watchApp(
          (event) => {
            switch (event.event_type) {
              case "spectrum_update":
                setSpectrum(event);
                break;
              case "library_updated":
                void refreshImages();
                break;
              // Nothing here chooses an audio device or monitors input yet; the
              // shell receives from a SpyServer. Named so that adding either
              // feature is a change to this list rather than a discovery.
              case "device_changed":
              case "monitor_state":
                break;
              case "__unknown__":
                console.debug("unhandled app event", event.raw.event_type);
                break;
            }
          },
          // Count connections rather than act on them. The handler is
          // installed once and would otherwise close over a stale session;
          // a counter in state lets an effect that *does* see the current
          // session react to it.
          () => setEngineReachedAt((n) => n + 1),
        );
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

  /** Ask the engine what a session is actually doing, and believe it.
   *
   *  The socket is a live feed, not a log. If it drops mid-decode and the
   *  session ends while it is down, the `decode_complete` or `error` that
   *  ended it is simply gone, and the window would otherwise show
   *  "listening" forever -- a session that looks healthy while nothing is
   *  happening, which is exactly the failure of 2026-08-19.
   *
   *  Only terminal states are reconciled. A live session's detail is richer
   *  on the socket than in the status payload, so overwriting "decoding
   *  MartinM1 at 60%" with a coarser reading would be a downgrade. */
  const resync = useCallback(async (sessionId: string) => {
    let status;
    try {
      status = await decodeStatus(sessionId);
    } catch (error) {
      // A session the engine does not have is a session that is not
      // running. This is what a restarted engine looks like from here:
      // the socket reconnects to a new process that never knew the id,
      // and swallowing the 404 left the window saying "Listening" for a
      // decode that no longer existed. Found by restarting the engine
      // under a live session and watching the status stay put.
      if ((error as CoreError).code === "SESSION_NOT_FOUND") {
        setSession(null);
        setLevelDb(null);
        setPosture({
          kind: "failed",
          message: "The decode stopped: the engine restarted and lost it.",
          action: "Start listening again.",
          code: "SESSION_NOT_FOUND",
        });
        return;
      }
      // Any other failure: the socket's own reconnect is still running
      // and will try again. Saying something wrong is worse than saying
      // nothing.
      return;
    }
    if (status.state === "listening" || status.state === "decoding") return;

    if (status.state === "completed") {
      setPosture({
        kind: "complete",
        imageId: status.image_id,
        mode: status.mode,
        rsv: null,
        fskid: null,
      });
      if (status.image_id) {
        setCompletedUrl(imageUrl(`/api/v1/images/${status.image_id}/file`));
      }
      void refreshImages();
      return;
    }
    setPosture({
      kind: "failed",
      // The status payload carries the engine's error string but not the
      // error code or suggested action the socket event would have had, so
      // this says plainly that it is a reconstruction.
      message:
        status.error ??
        "The decode ended while I wasn't connected, and I don't know why.",
      action: "Start listening again.",
      code: "RECONCILED",
    });
  }, [refreshImages]);

  useEffect(() => {
    // Nothing to reconcile before the first connection, or with no decode.
    if (engineReachedAt === 0 || !session) return;
    // Not a cascading render: resync awaits a request before it touches
    // any state, so nothing is set synchronously here. The rule cannot
    // see past the call.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void resync(session);
  }, [engineReachedAt, session, resync]);

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
      closeSession.current = watchSession(
        started.session_id,
        (event) => {
          switch (event.event_type) {
            case "audio_levels":
              setLevelDb(event.left_db);
              break;
            case "vis_detected":
              setPosture({
                kind: "decoding",
                mode: event.mode,
                confidence: event.confidence,
              });
              break;
            case "scanline_update":
              setScanline(event);
              break;
            case "decode_complete": {
              setPosture({
                kind: "complete",
                imageId: event.image_id,
                mode: event.mode,
                rsv: event.rsv_report,
                fskid: event.fskid_detected
                  ? event.fskid_checksum_valid
                    ? "verified"
                    : "unverified"
                  : null,
              });
              if (event.image_id) {
                setCompletedUrl(imageUrl(`/api/v1/images/${event.image_id}/file`));
              }
              void refreshImages();
              break;
            }
            // The watcher found a picture on disk -- an import, or a decode
            // this window did not run. The log is a view of the library, so
            // it should show it without being asked twice.
            case "library_updated":
              void refreshImages();
              break;
            case "error": {
              const failure = event;
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
            // Reached only in v0.2, when this window can transmit. Named
            // rather than ignored by omission: the difference between a
            // decision and a gap is whether anyone wrote it down.
            case "tx_progress":
            case "transmit_complete":
              break;
            // A newer engine sent something this build has never heard of.
            // Worth one line in the console -- not worth interrupting an
            // operator who is waiting for a picture.
            case "__unknown__":
              console.debug("unhandled session event", event.raw.event_type);
              break;
          }
        },
        // On every connect, reconnects included. The socket is a live feed,
        // so anything the engine sent while it was down is gone -- including
        // the decode_complete or error that ended the session. Without this
        // the window shows "listening" for a decode the engine finished,
        // which is the 2026-08-19 stall wearing different clothes.
        () => void resync(started.session_id),
      );
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

  const frequencyHz = config?.spyserver_frequency_hz ?? BAND_FREQUENCIES["20m"];

  // Propagation is reported per band, so a custom frequency asks about the
  // band it sits in. Tuning uses the frequency itself; only this question
  // needs a name for it.
  const propagationBand = band ?? nearestBand(frequencyHz);

  useEffect(() => {
    let cancelled = false;
    const ask = () =>
      getPropagation(propagationBand)
        .then((report) => {
          if (cancelled) return;
          setPropagation(report);
          setPropagationProblem(null);
        })
        .catch((error: CoreError) => {
          if (cancelled) return;
          setPropagation(null);
          // Requirement 13: unreachable sources must look louder than good
          // news. A blank panel reads as "nothing to report", which is the
          // opposite of the truth.
          setPropagationProblem(error.message);
        });
    void ask();
    // The indices update a few times a day; a quarter of an hour is plenty.
    const timer = window.setInterval(ask, 15 * 60 * 1000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [propagationBand]);

  /** Pick a band, and remember it.
   *
   *  `decode/start` takes the band by name, so the decode does not need
   *  this; config stores a frequency, so persisting the choice does.
   *  Failing to save is not worth interrupting the operator -- the band
   *  they just pressed is still the band they are listening on.
   */
  const chooseBand = async (option: Band) => {
    setBand(option);
    try {
      const saved = await patchConfig({
        spyserver_frequency_hz: BAND_FREQUENCIES[option],
      });
      setConfig(saved);
    } catch {
      /* It will be right for this session and wrong after a restart. */
    }
  };

  const listen = () => begin(() => startSpyServerDecode(band, 3600));
  const replay = (filePath: string) => begin(() => startFileDecode(filePath));

  const stop = async () => {
    if (session) {
      try {
        await stopDecode(session);
      } catch (error) {
        const failure = error as CoreError;

        // A session the engine has never heard of is a session that is not
        // running, which is what Stop was for. Sessions live in the
        // engine's memory, so restarting it loses them -- and treating
        // that as "still decoding" traps the operator behind a Stop button
        // that can never succeed. Found by doing it: kill the engine
        // mid-listen, press Stop, bring the engine back, press Stop again.
        if (failure.code !== "SESSION_NOT_FOUND") {
          // A stop that did not take, reported as idle, is the worst of the
          // three outcomes: the radio is half-duplex, so the engine is
          // still holding the session and the next Listen comes back 409
          // for something the operator believes they already stopped.
          setPosture({
            kind: "failed",
            message: `I couldn't stop the decode. ${failure.message}`,
            action: failure.suggestedAction ?? "Try Stop again.",
            code: failure.code ?? "STOP_FAILED",
            retryStop: true,
          });
          return;
        }
      }
    }
    closeSession.current?.();
    closeSession.current = null;
    setSession(null);
    setPosture({ kind: "idle" });
    setLevelDb(null);
  };

  // Stop, not Listen, while the engine may still hold the session. Offering
  // Listen after a failed stop sends the operator into a 409 for a decode
  // they believe they already ended.
  // Where the picture that just finished was heard. The decode_complete
  // event does not carry it -- provenance lives on the library row -- and a
  // decode that was worth recording is worth being able to place six months
  // later (#139), which means saying so at the moment it lands and not only
  // in the log.
  const heardOn =
    posture.kind === "complete" && posture.imageId
      ? (images.find((row) => row.id === posture.imageId) ?? null)
      : null;

  const live =
    posture.kind === "listening" ||
    posture.kind === "decoding" ||
    (posture.kind === "failed" && posture.retryStop === true);

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

  /** Move a control, then show what the engine says is in force.
   *
   *  The optimistic set is what keeps the slider from lagging the thumb.
   *  The correction afterwards is what stops it lying: `applied` is read
   *  back from the running decode, so a value that was clamped, or that
   *  the open source could not take, comes back different from what was
   *  asked for -- and `ignored` names it when the control did nothing at
   *  all. Both used to be discarded by `.catch(() => undefined)`, which
   *  showed every adjustment as successful including the refused ones.
   */
  const push = async (changes: DecodeAdjustment, optimistic: () => void) => {
    optimistic();
    if (!session) return;

    let answer;
    try {
      answer = await adjustDecode(session, changes);
    } catch (error) {
      setAdjustment((error as CoreError).message);
      return;
    }

    // The engine has the last word on what the decode is using.
    if (answer.applied.input_gain !== undefined) setGain(answer.applied.input_gain);
    if (answer.applied.auto_squelch !== undefined) setSquelch(answer.applied.auto_squelch);
    setAdjustment(null);
  };

  const pushGain = (value: number) =>
    push({ input_gain: value }, () => setGain(value));

  const pushSquelch = (value: boolean) =>
    push({ auto_squelch: value }, () => setSquelch(value));

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
        {band === null && (
          <span className="mono tuned" title="Not one of the band presets">
            {(frequencyHz / 1000).toFixed(1)} kHz
          </span>
        )}
        <div className="bands" role="group" aria-label="Band">
          {BANDS.map((option) => (
            <button
              key={option}
              className={option === band ? "band on" : "band"}
              onClick={() => void chooseBand(option)}
              disabled={live}
            >
              {option}
            </button>
          ))}
        </div>
        <Propagation
          report={propagation}
          problem={propagationProblem}
          open={indicesOpen}
          onToggle={() => setIndicesOpen((was) => !was)}
        />
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
        <Canvas
          scanline={scanline}
          frame={frame}
          scale={scale}
          completedUrl={completedUrl}
          failed={posture.kind === "failed"}
        />
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
              onChange={(event) => void pushGain(Number(event.target.value))}
            />
            <span className="mono value">{gain.toFixed(2)}×</span>
          </label>
          <label className="control checkbox">
            <input
              type="checkbox"
              checked={squelch}
              onChange={(event) => void pushSquelch(event.target.checked)}
            />
            Squelch
          </label>
          {adjustment && (
            <span className="control-note" role="status">
              {adjustment}
            </span>
          )}
          <span className="spacer" />
          <Status
            posture={posture}
            levelDb={levelDb}
            scanline={scanline}
            spectrum={spectrum}
            heardOn={heardOn}
          />
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
          <p className="empty">
            Nothing decoded yet. The band is quiet most of the time.
            {propagation && ` ${propagation.explanation}`}
          </p>
        )}
        <div className="rows">
          {images.map((row) => (
            <figure key={row.id} className="row">
              <button
                type="button"
                className="open-picture"
                onClick={() => setViewing(row)}
                // The thumbnail is ~120px wide: enough to see that a
                // picture arrived, not enough to read a callsign off it,
                // which is the whole reason for opening it.
                title="See the whole picture"
              >
                <img
                  src={imageUrl(row.thumbnail_url ?? row.url)}
                  alt={`${row.mode ?? "Unknown mode"} decoded at ${heardAt(row.timestamp)}`}
                />
              </button>
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

      {viewing && <Viewer row={viewing} onClose={() => setViewing(null)} />}

      {settingsOpen && config && (
        <Settings
          config={config}
          onReplay={(path) => {
            setSettingsOpen(false);
            void replay(path);
          }}
          onClose={() => setSettingsOpen(false)}
          onSaved={(saved) => {
            setConfig(saved);
            // The frequency may have moved off a preset, or onto one. The
            // buttons have to agree with the radio: leaving 40m lit while
            // the saved frequency is 14.233 is a control stating something
            // that is not true.
            setBand(bandFor(saved.spyserver_frequency_hz) ?? null);
            setSettingsOpen(false);
          }}
        />
      )}
    </div>
  );
}

/** Whether the band should be carrying signal.
 *
 * One sentence, not a dashboard (requirement 13). The indices sit behind
 * disclosure for operators who read them; they are not the deliverable.
 * And it states support, never activity: an open band does not promise
 * anybody will transmit.
 */
function Propagation({
  report,
  problem,
  open,
  onToggle,
}: {
  report: Propagation | null;
  problem: string | null;
  open: boolean;
  onToggle: () => void;
}) {
  if (problem) {
    return (
      <button className="propagation unknown" onClick={onToggle} title={problem}>
        no propagation report
      </button>
    );
  }
  if (!report) return null;

  return (
    <div className="propagation-wrap">
      <button
        className={`propagation ${report.state.toLowerCase()}`}
        onClick={onToggle}
        title={report.explanation}
        aria-expanded={open}
      >
        {report.band} {report.state.toLowerCase()}
      </button>
      {open && (
        <div className="indices">
          <p>{report.explanation}</p>
          <dl className="mono">
            <div><dt>SFI</dt><dd>{report.solar_flux}</dd></div>
            <div><dt>K</dt><dd>{report.k_index}</dd></div>
            <div><dt>A</dt><dd>{report.a_index || "—"}</dd></div>
            <div><dt>Sunspots</dt><dd>{report.sunspots || "—"}</dd></div>
            <div><dt>X-ray</dt><dd>{report.xray || "—"}</dd></div>
          </dl>
          {report.updated && <p className="muted">Updated {report.updated}</p>}
          {report.source_errors.length > 0 && (
            <p className="partial">
              Partial report: {report.source_errors.join("; ")}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function Status({
  posture,
  levelDb,
  scanline,
  spectrum,
  heardOn,
}: {
  posture: Posture;
  levelDb: number | null;
  scanline: ScanlineUpdate | null;
  spectrum: SpectrumUpdate | null;
  /** The library row for a picture that just finished, if it is known. */
  heardOn: ImageRow | null;
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
          {[
            posture.mode,
            posture.rsv,
            posture.fskid && `FSKID ${posture.fskid}`,
            // Where it was heard, said now rather than only in the log. A
            // remote reception is not a contact, and that is the fact most
            // easily lost between the decode and the logbook (#139).
            heardOn?.heard_at === "remote"
              ? `heard at ${heardOn.receiver ?? "another receiver"}`
              : heardOn?.heard_at === "my_station"
                ? "my station"
                : heardOn?.source === "file"
                  ? "from a recording"
                  : null,
          ]
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

/** One picture, as large as the window allows.
 *
 *  The log's thumbnails are ~120px: enough to see that something arrived,
 *  not enough to read a callsign, which is what an operator actually wants
 *  from a picture they heard hours ago. Borrowing the window rather than
 *  opening a second one keeps the single-window model intact -- the same
 *  thing Settings does.
 */
function Viewer({ row, onClose }: { row: ImageRow; onClose: () => void }) {
  useEffect(() => {
    // Escape closes it. A picture viewer that can only be dismissed by
    // finding a small button is a picture viewer you stop opening.
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="scrim" onClick={onClose}>
      <figure className="viewer" onClick={(event) => event.stopPropagation()}>
        <img
          src={imageUrl(row.url)}
          alt={`${row.mode ?? "Unknown mode"} decoded at ${heardAt(row.timestamp)}`}
        />
        <figcaption>
          <span className="mono">{heardAt(row.timestamp)}</span>
          <span>{row.mode ?? "unknown mode"}</span>
          {row.callsign && <span className="call">{row.callsign}</span>}
          {row.rsv_report && <span className="mono rsv">{row.rsv_report}</span>}
          <span className={row.heard_at === "remote" ? "where remote" : "where"}>
            {row.heard_at === "remote"
              ? `heard at ${row.receiver ?? "another receiver"}`
              : row.heard_at === "my_station"
                ? "my station"
                : row.source === "file"
                  ? "from a recording"
                  : "source unknown"}
          </span>
          <button type="button" onClick={onClose}>
            Close
          </button>
        </figcaption>
      </figure>
    </div>
  );
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
  // In kHz, because that is how an operator says it: 14230, not 14230000.
  const [frequencyKHz, setFrequencyKHz] = useState(
    String(config.spyserver_frequency_hz / 1000),
  );
  const [stallTimeout, setStallTimeout] = useState(
    String(config.spyserver_stall_timeout_sec ?? 5),
  );
  const [libraryPath, setLibraryPath] = useState(config.image_library_path ?? "");
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
          spyserver_frequency_hz: Math.round(Number(frequencyKHz) * 1000),
          spyserver_stall_timeout_sec: Number(stallTimeout),
          image_library_path: libraryPath.trim(),
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
          Frequency (kHz)
          <input
            type="number"
            min={0}
            step={0.1}
            value={frequencyKHz}
            onChange={(event) => setFrequencyKHz(event.target.value)}
          />
        </label>
        <p className="note">
          The band buttons set this. Type one in for a frequency that is not
          a button — 14233, say — and the buttons will show none selected,
          because none of them is where the radio is.
        </p>
        <label>
          Give up after
          <input
            type="number"
            min={1}
            max={120}
            step={1}
            value={stallTimeout}
            onChange={(event) => setStallTimeout(event.target.value)}
          />
        </label>
        <p className="note">
          Seconds of silence before I decide the stream has died rather than
          the band being quiet. A network receiver can stop sending without
          closing the connection, and on 2026-08-19 a session listened to a
          frozen buffer for three and a half hours.
        </p>
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
        <h2>Pictures</h2>
        <label>
          Library folder
          <input
            value={libraryPath}
            onChange={(event) => setLibraryPath(event.target.value)}
            placeholder="~/.ssteve/images"
          />
        </label>
        <p className="note">
          Where decoded pictures are written, and watched: anything you drop
          in here joins the log. They are ordinary files -- the database
          only remembers what was heard, never the pictures themselves.
        </p>

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
