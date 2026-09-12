//! Starting and stopping the SSTeVe engine (#143).
//!
//! The engine is a separate process: a frozen Python build shipped beside the
//! app as a Tauri sidecar. The window is a client of it, exactly as the CLI
//! is, which is the property the whole architecture rests on.
//!
//! Three things this has to get right:
//!
//! 1. **Pick a port rather than assume one.** A second copy of the app must
//!    not fight the first for 8000.
//! 2. **Reuse an engine that is already there.** A developer running
//!    `uv run sstv-server` should not get a second one spawned over the top.
//! 3. **Leave nothing behind.** A decode holds a radio's audio input, and a
//!    transmit can leave a radio keyed; an orphaned engine is not a tidiness
//!    problem.

use std::io::{Read, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::PathBuf;
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{AppHandle, Manager, State};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

/// Where the engine is, and whether we are the ones running it.
pub struct Engine {
    pub base_url: String,
    child: Option<CommandChild>,
}

#[derive(Default)]
pub struct EngineState {
    pub engine: Mutex<Option<Engine>>,
    /// Why the engine is not running, kept so the window can say so. Asked
    /// for only when a request fails, which avoids the window having to
    /// work out whether it is running inside Tauri at all.
    pub problem: Mutex<Option<String>>,
}

/// The port a developer's own `uv run sstv-server` uses.
const DEFAULT_PORT: u16 = 8000;

/// How long to wait for the engine to answer before giving up. Cold start is
/// about a second once warm, but the first launch of an unsigned bundle can
/// spend far longer in Gatekeeper before any of our code runs.
const READY_TIMEOUT: Duration = Duration::from_secs(90);

/// Is something already serving the engine's API on this port?
///
/// One request over a socket rather than an HTTP crate: the question is
/// small, it is always loopback, and every timeout here wants to be explicit.
/// A bare TCP connect would not do -- anything can hold a port; only a 200
/// from the engine's own route proves what is behind it.
fn already_serving(port: u16) -> bool {
    let address = SocketAddr::from(([127, 0, 0, 1], port));
    let Ok(mut stream) = TcpStream::connect_timeout(&address, Duration::from_millis(300)) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_millis(600)));
    let _ = stream.set_write_timeout(Some(Duration::from_millis(600)));

    let request = format!(
        "GET /api/v1/config HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n"
    );
    if stream.write_all(request.as_bytes()).is_err() {
        return false;
    }

    let mut head = [0_u8; 15];
    let mut filled = 0;
    while filled < head.len() {
        match stream.read(&mut head[filled..]) {
            Ok(0) => break,
            Ok(read) => filled += read,
            Err(_) => return false,
        }
    }
    String::from_utf8_lossy(&head[..filled]).starts_with("HTTP/1.1 200")
}

/// A port nobody is using, asked of the OS rather than guessed.
fn free_port() -> std::io::Result<u16> {
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let port = listener.local_addr()?.port();
    drop(listener);
    Ok(port)
}

/// Start the engine, or adopt one that is already running.
pub fn start(app: &AppHandle) -> Result<Engine, String> {
    if already_serving(DEFAULT_PORT) {
        // Someone else's engine -- a developer's, or another copy of this app.
        // Use it and do not take ownership: we must not kill what we did not
        // start.
        return Ok(Engine {
            base_url: format!("http://127.0.0.1:{DEFAULT_PORT}"),
            child: None,
        });
    }

    let executable = locate(app)?;
    let port = free_port().map_err(|error| format!("no free port to give the engine: {error}"))?;
    let (mut events, child) = app
        .shell()
        .command(executable)
        .args(["--port", &port.to_string()])
        .spawn()
        .map_err(|error| format!("the engine would not start: {error}"))?;

    let deadline = Instant::now() + READY_TIMEOUT;
    while Instant::now() < deadline {
        if already_serving(port) {
            return Ok(Engine {
                base_url: format!("http://127.0.0.1:{port}"),
                child: Some(child),
            });
        }

        // Watch the process as well as the port. A child that dies on
        // startup -- a missing library, a bad build -- would otherwise leave
        // the window saying "starting the engine" for the full timeout, when
        // the answer arrived in the first second.
        while let Ok(event) = events.try_recv() {
            if let CommandEvent::Terminated(payload) = event {
                return Err(match payload.code {
                    Some(code) => format!("the engine stopped straight away (exit {code})"),
                    None => "the engine stopped straight away".to_string(),
                });
            }
        }

        std::thread::sleep(Duration::from_millis(200));
    }

    // Do not leave it running: a half-started engine holding the radio is
    // worse than none.
    let _ = child.kill();
    Err(format!(
        "the engine started but never answered on port {port}"
    ))
}

/// Find the frozen engine.
///
/// It ships as a **directory** rather than a lone executable: a one-folder
/// PyInstaller build locates its `_internal` siblings by its own path, so
/// copying the executable alone produces something that starts and dies
/// looking for libpython. A one-file build would avoid that and re-extract
/// 205 MB on every launch instead, turning a 0.9 s start into a wait.
///
/// In a packaged app it lives in the bundle's resources. In `tauri dev`
/// there may be no resource directory yet, so the repository build is the
/// fallback -- which is also what a developer wants after rebuilding it.
fn locate(app: &AppHandle) -> Result<PathBuf, String> {
    let mut candidates: Vec<PathBuf> = Vec::new();

    if let Ok(resources) = app.path().resource_dir() {
        candidates.push(resources.join("engine").join("sstv-server"));
    }
    // The repository layout, for `tauri dev` before anything is bundled.
    if let Ok(current) = std::env::current_dir() {
        candidates.push(
            current
                .join("..")
                .join("src-tauri")
                .join("binaries")
                .join("engine")
                .join("sstv-server"),
        );
        candidates.push(
            current
                .join("src-tauri")
                .join("binaries")
                .join("engine")
                .join("sstv-server"),
        );
    }

    candidates
        .into_iter()
        .find(|path| path.exists())
        .ok_or_else(|| {
            "the engine is missing from this build -- run \
             `uv run python scripts/build_engine.py` from sstv_core/"
                .to_string()
        })
}

/// Stop the engine, if this app is the one that started it.
pub fn stop(state: &EngineState) {
    if let Ok(mut guard) = state.engine.lock() {
        if let Some(engine) = guard.take() {
            if let Some(child) = engine.child {
                let _ = child.kill();
            }
        }
    }
}

/// Where the window should send its requests.
///
/// The frontend asks rather than assuming, because the port is chosen at
/// runtime. Returns an error string the UI can show: "the engine isn't
/// running" is a first-run state, not a crash.
#[tauri::command]
pub fn engine_base_url(state: State<'_, EngineState>) -> Result<String, String> {
    state
        .engine
        .lock()
        .map_err(|_| "the engine state is unreadable".to_string())?
        .as_ref()
        .map(|engine| engine.base_url.clone())
        .ok_or_else(|| "the engine is not running".to_string())
}

/// What went wrong when the engine was started, if anything.
///
/// The window asks after a request fails, and shows this instead of its own
/// guess: "the engine stopped straight away (exit 1)" is worth more than
/// "I can't reach it".
#[tauri::command]
pub fn engine_problem(state: State<'_, EngineState>) -> Option<String> {
    state.problem.lock().ok().and_then(|guard| guard.clone())
}

/// Record why there is no engine, for the window to ask about later.
pub fn remember_problem(app: &AppHandle, problem: String) {
    let state = app.state::<EngineState>();
    let Ok(mut guard) = state.problem.lock() else {
        return;
    };
    *guard = Some(problem);
}

/// Called by the window once it is ready, so a failure to start has somewhere
/// to be reported rather than being lost before anything could listen.
pub fn remember(app: &AppHandle, engine: Engine) {
    let state = app.state::<EngineState>();
    let Ok(mut guard) = state.engine.lock() else {
        return;
    };
    *guard = Some(engine);
}
