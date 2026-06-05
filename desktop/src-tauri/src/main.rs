// OpenConstructionERP Desktop, Tauri v2 application.
//
// Manages the FastAPI backend as a sidecar process.
// The React frontend loads in a native webview window.
// Backend communicates via http://localhost:{port}/api/
//
// Robustness contract (why this file is defensive):
//   In release builds the process has no console (windows_subsystem = "windows"),
//   so any panic dies silently and, if it happens inside setup(), the window
//   never appears. That is exactly the "I click the icon and nothing happens"
//   failure. So setup() must NEVER panic: every fallible step is handled, the
//   splash window is kept open, a human-readable error is shown via setError(),
//   and a full diagnostic log is always written to
//   ~/.openestimate/desktop-launcher.log (alongside the backend's own data).

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};

use tauri::{
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager, RunEvent,
};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

struct AppState {
    /// Handle to the spawned backend process so it survives past setup() and
    /// can be killed when the app exits.
    backend_child: Mutex<Option<CommandChild>>,
}

/// Resolve the user's home directory without pulling in extra crates.
fn home_dir() -> Option<PathBuf> {
    for var in ["USERPROFILE", "HOME"] {
        if let Ok(p) = std::env::var(var) {
            if !p.is_empty() {
                return Some(PathBuf::from(p));
            }
        }
    }
    None
}

/// Path of the launcher diagnostic log (same folder the backend uses for data).
fn log_path() -> Option<PathBuf> {
    home_dir().map(|h| h.join(".openestimate").join("desktop-launcher.log"))
}

/// Append one line to the diagnostic log (best effort) and to stderr.
///
/// This is the single most important diagnostic when a user reports "nothing
/// happens": even if the window never paints, the log records how far startup
/// got and the exact error.
fn log_line(msg: &str) {
    let secs = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let line = format!("[{secs}] {msg}\n");

    if let Some(path) = log_path() {
        if let Some(parent) = path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        use std::io::Write;
        if let Ok(mut f) = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&path)
        {
            let _ = f.write_all(line.as_bytes());
        }
    }
    eprintln!("{}", line.trim_end());
}

/// Escape a string for embedding inside a single-quoted JavaScript literal.
fn js_escape(s: &str) -> String {
    s.replace('\\', "\\\\")
        .replace('\'', "\\'")
        .replace('\n', " ")
        .replace('\r', " ")
}

/// Show a fatal error on the splash screen without ever panicking.
///
/// setup() may run before the splash page has finished loading its inline
/// script, so we retry the eval a few times over ~2 seconds. setError() is
/// idempotent (it just sets text), so repeated calls are harmless.
fn report_fatal(handle: &tauri::AppHandle, message: &str) {
    let handle = handle.clone();
    let msg = js_escape(message);
    tauri::async_runtime::spawn(async move {
        for _ in 0..8 {
            if let Some(window) = handle.get_webview_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
                let _ = window.eval(&format!(
                    "(function(){{if(typeof setError==='function'){{setError('{msg}');}}}})()"
                ));
            }
            tokio::time::sleep(std::time::Duration::from_millis(250)).await;
        }
    });
}

/// Find an available port for the backend server, with a fixed fallback so a
/// picker failure never aborts startup.
fn find_available_port() -> u16 {
    portpicker::pick_unused_port().unwrap_or(8732)
}

/// Wait for the backend health endpoint to respond.
///
/// Polls `/api/health` every ~500ms until it succeeds or the timeout elapses.
/// While waiting, updates the splash screen so the user sees progress; first-run
/// embedded-PostgreSQL setup can be slow.
async fn wait_for_backend(handle: &tauri::AppHandle, port: u16, timeout_secs: u64) -> bool {
    let client = reqwest::Client::new();
    let url = format!("http://127.0.0.1:{port}/api/health");
    let start = std::time::Instant::now();
    let mut progress_shown = false;

    while start.elapsed().as_secs() < timeout_secs {
        if let Ok(resp) = client.get(&url).send().await {
            if resp.status().is_success() {
                return true;
            }
        }

        if !progress_shown && start.elapsed().as_secs() >= 8 {
            progress_shown = true;
            if let Some(window) = handle.get_webview_window("main") {
                let _ = window.eval("setStatus('Setting up the local database, almost there')");
            }
        }

        tokio::time::sleep(std::time::Duration::from_millis(500)).await;
    }
    false
}

fn main() {
    let port = find_available_port();

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .manage(AppState {
            backend_child: Mutex::new(None),
        })
        .setup(move |app| {
            let handle = app.handle().clone();
            log_line(&format!("launcher starting; backend port = {port}"));

            // Tray icon is a nice-to-have; never let its failure abort startup.
            match TrayIconBuilder::new()
                .tooltip("OpenConstructionERP")
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        if let Some(window) = tray.app_handle().get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                })
                .build(app)
            {
                Ok(_) => {}
                Err(e) => log_line(&format!("warning: tray icon build failed (non-fatal): {e}")),
            }

            // Start the backend sidecar.
            //
            // The "serve" subcommand is required: the CLI only accepts --host /
            // --port under a subcommand. Invoked bare it would ignore them,
            // fall back to defaults, and on first run block on an interactive
            // "open in browser?" stdin prompt that a sidecar has no terminal
            // for. With --data-dir left unset the sidecar uses its default
            // (~/.openestimate), which stays writable even for a per-machine
            // install under Program Files.
            let shell = handle.shell();
            let sidecar_cmd = match shell.sidecar("openestimate-server") {
                Ok(cmd) => {
                    cmd.args(["serve", "--host", "127.0.0.1", "--port", &port.to_string()])
                }
                Err(e) => {
                    log_line(&format!("FATAL: cannot create sidecar command: {e}"));
                    report_fatal(
                        &handle,
                        "Could not locate the backend component. Please reinstall the \
application. A log was saved under your home folder as .openestimate/desktop-launcher.log.",
                    );
                    // Keep the window open so the user sees the error.
                    return Ok(());
                }
            };

            let (mut rx, child) = match sidecar_cmd.spawn() {
                Ok(pair) => pair,
                Err(e) => {
                    log_line(&format!("FATAL: cannot spawn sidecar: {e}"));
                    report_fatal(
                        &handle,
                        "The backend component could not be started. Some antivirus tools \
block newly installed programs; allow OpenConstructionERP and try again. A log was saved \
under your home folder as .openestimate/desktop-launcher.log.",
                    );
                    return Ok(());
                }
            };
            log_line("sidecar spawned");

            // Keep the child handle alive (and killable on exit).
            {
                let state = handle.state::<AppState>();
                *state.backend_child.lock().unwrap() = Some(child);
            }

            let backend_ready = Arc::new(AtomicBool::new(false));
            let last_stderr = Arc::new(Mutex::new(String::new()));

            // Pump the sidecar's output into the log file and remember recent
            // stderr so a startup crash can be shown to the user verbatim.
            {
                let ready = backend_ready.clone();
                let stderr_buf = last_stderr.clone();
                let handle_evt = handle.clone();
                tauri::async_runtime::spawn(async move {
                    while let Some(event) = rx.recv().await {
                        match event {
                            CommandEvent::Stdout(bytes) => {
                                let line = String::from_utf8_lossy(&bytes);
                                log_line(&format!("[backend] {}", line.trim_end()));
                            }
                            CommandEvent::Stderr(bytes) => {
                                let line = String::from_utf8_lossy(&bytes);
                                log_line(&format!("[backend:err] {}", line.trim_end()));
                                let mut buf = stderr_buf.lock().unwrap();
                                buf.push_str(&line);
                                if buf.len() > 4000 {
                                    let cut = buf.len() - 4000;
                                    *buf = buf[cut..].to_string();
                                }
                            }
                            CommandEvent::Error(err) => {
                                log_line(&format!("[backend:error] {err}"));
                            }
                            CommandEvent::Terminated(payload) => {
                                log_line(&format!(
                                    "[backend] terminated: code={:?} signal={:?}",
                                    payload.code, payload.signal
                                ));
                                // If the backend died before ever becoming
                                // healthy, surface it now instead of leaving the
                                // user staring at the spinner for the full timeout.
                                if !ready.load(Ordering::SeqCst) {
                                    let tail = stderr_buf.lock().unwrap().clone();
                                    let detail = if tail.trim().is_empty() {
                                        format!(
                                            "The backend stopped unexpectedly (exit code {:?}) \
before it finished starting. A log was saved under your home folder as \
.openestimate/desktop-launcher.log.",
                                            payload.code
                                        )
                                    } else {
                                        format!(
                                            "The backend stopped unexpectedly during startup: {} \
(full log in .openestimate/desktop-launcher.log)",
                                            tail.trim()
                                        )
                                    };
                                    report_fatal(&handle_evt, &detail);
                                }
                                break;
                            }
                            _ => {}
                        }
                    }
                });
            }

            // Wait for the backend to be ready, then navigate the webview from
            // the splash screen to the live application. First-run embedded
            // PostgreSQL setup (initdb, migrations, module load, demo seed) can
            // be slow on a cold machine, so allow up to 240 seconds.
            let handle_clone = handle.clone();
            let ready_flag = backend_ready.clone();
            tauri::async_runtime::spawn(async move {
                if wait_for_backend(&handle_clone, port, 240).await {
                    ready_flag.store(true, Ordering::SeqCst);
                    log_line("backend healthy; navigating to app");
                    if let Some(window) = handle_clone.get_webview_window("main") {
                        let url = format!("http://127.0.0.1:{port}/");
                        let _ = window.show();
                        let _ = window.set_focus();
                        let _ = window.eval(&format!("window.location.replace('{url}')"));
                    }
                } else {
                    log_line("backend did not become healthy within 240s");
                    // If the sidecar already reported termination, that handler
                    // showed a precise error; only show the generic timeout if
                    // startup is genuinely still pending.
                    if !ready_flag.load(Ordering::SeqCst) {
                        report_fatal(
                            &handle_clone,
                            "The application backend did not start in time. Please close this \
window and try again. If the problem persists, a log was saved under your home folder as \
.openestimate/desktop-launcher.log; please send it to info@datadrivenconstruction.io.",
                        );
                    }
                }
            });

            Ok(())
        })
        .build(tauri::generate_context!());

    match app {
        Ok(app) => app.run(|app_handle, event| {
            if let RunEvent::ExitRequested { .. } = event {
                // Stop the backend sidecar so it does not linger after close.
                let state = app_handle.state::<AppState>();
                if let Some(child) = state.backend_child.lock().unwrap().take() {
                    let _ = child.kill();
                }
            }
        }),
        Err(e) => {
            // Building the Tauri app itself failed. There is no window to show
            // an error in, so at least leave a breadcrumb in the log.
            log_line(&format!("FATAL: error building Tauri application: {e}"));
        }
    }
}
