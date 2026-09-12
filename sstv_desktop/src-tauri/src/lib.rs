mod engine;

use engine::{Engine, EngineState};
use tauri::{Manager, RunEvent};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .manage(EngineState::default())
        .invoke_handler(tauri::generate_handler![
            engine::engine_base_url,
            engine::engine_problem
        ])
        .setup(|app| {
            // Start the engine before the window asks for it. A failure here
            // is reported through engine_base_url rather than thrown: the
            // window can then say what went wrong, where a panic would give
            // an empty frame and no explanation.
            match engine::start(app.handle()) {
                Ok(started) => engine::remember(app.handle(), started),
                Err(problem) => {
                    eprintln!("SSTeVe engine: {problem}");
                    engine::remember_problem(app.handle(), problem);
                }
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building the SSTeVe window")
        .run(|app, event| {
            // Stop what we started. A decode holds the radio's audio input and
            // a transmit can leave it keyed, so an orphaned engine is not
            // merely untidy.
            if let RunEvent::ExitRequested { .. } | RunEvent::Exit = event {
                engine::stop(&app.state::<EngineState>());
            }
        });
}

// Re-exported so the type is nameable from tests later.
pub use engine::Engine as SSTVeEngine;
const _: fn() = || {
    let _ = std::mem::size_of::<Engine>();
};
