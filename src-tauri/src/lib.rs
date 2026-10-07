use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;

use tauri::{Manager, RunEvent};

/// Keeps the spawned backend process so it can be shut down cleanly when the app closes;
/// otherwise a Python process is left hanging around (see docs/phases/phase-12-desktop-packaging.md,
/// "Definition of Done": Task Manager must show no orphan process).
struct BackendProcess(Mutex<Option<Child>>);

/// Backend executable name inside the PyInstaller folder.
const BACKEND_BIN: &str = if cfg!(windows) { "viedub-backend.exe" } else { "viedub-backend" };

/// Path to the backend executable: dev mode points straight at the PyInstaller build folder
/// (`backend/dist/viedub-backend/`, relative to the CWD `src-tauri/` when `tauri dev`
/// runs); the packaged build uses the resource bundled via
/// `tauri.conf.json` (`bundle.resources`).
fn resolve_backend_exe(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    if cfg!(debug_assertions) {
        let dev_path = PathBuf::from("../backend/dist/viedub-backend").join(BACKEND_BIN);
        if !dev_path.exists() {
            return Err(format!(
                "Không tìm thấy backend đã build ở {:?} — chạy `pyinstaller` trong backend/ trước \
                 (xem docs/phases/phase-12-desktop-packaging.md).",
                dev_path
            ));
        }
        return Ok(dev_path);
    }

    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|e| format!("Không lấy được resource_dir: {e}"))?;
    Ok(resource_dir.join("backend").join(BACKEND_BIN))
}

/// Port the backend listens on. The packaged build asks the OS for a FREE port instead of
/// hard-coding 8000: the user's machine may already have other software (or an old app
/// instance that has not fully exited) on 8000, and the UI would talk to a stranger process.
/// Dev mode keeps 8000 because the dev frontend (Vite) hard-codes it.
fn pick_backend_port() -> u16 {
    if cfg!(debug_assertions) {
        return 8000;
    }
    std::net::TcpListener::bind(("127.0.0.1", 0))
        .and_then(|listener| listener.local_addr())
        .map(|addr| addr.port())
        .unwrap_or(8000)
}

fn spawn_backend(app: &tauri::AppHandle, port: u16) -> Result<Child, String> {
    let exe_path = resolve_backend_exe(app)?;
    let mut command = Command::new(&exe_path);
    command.env("BACKEND_PORT", port.to_string());
    // The backend writes its log to a file (see backend/app/core/logging_setup.py), so no
    // console is needed: null handles keep valid stdout/stderr for Python.
    command
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    // Without this flag Windows opens a cmd window for every console sidecar.
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }

    command
        .spawn()
        .map_err(|e| format!("Không khởi động được backend ({:?}): {e}", exe_path))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(BackendProcess(Mutex::new(None)))
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            let handle = app.handle().clone();
            let port = pick_backend_port();
            match spawn_backend(&handle, port) {
                Ok(child) => {
                    log::info!("Backend đã khởi động, pid={}", child.id());
                    let state = handle.state::<BackendProcess>();
                    *state.0.lock().unwrap() = Some(child);
                }
                Err(e) => {
                    log::error!("{e}");
                    return Err(e.into());
                }
            }

            // The window is created here (not by tauri.conf.json) so the backend address can
            // be injected into the page BEFORE the frontend runs; `frontend/src/lib/api.ts` reads
            // `window.__VIEDUB_API_BASE__`.
            let window_config = app.config().app.windows[0].clone();
            tauri::WebviewWindowBuilder::from_config(app, &window_config)?
                .initialization_script(format!(
                    "window.__VIEDUB_API_BASE__ = 'http://127.0.0.1:{port}';"
                ))
                .build()?;

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            // Shut the backend process down cleanly when the app closes, to avoid leaving a
            // background Python process behind (see the DoD in docs/phases/phase-12-desktop-packaging.md).
            if let RunEvent::Exit = event {
                let state = app_handle.state::<BackendProcess>();
                // Take the Child out of the Mutex and release the lock right away (do not
                // hold the lock while killing/waiting: that is blocking I/O).
                let child_opt = state.0.lock().unwrap().take();
                if let Some(mut child) = child_opt {
                    let _ = child.kill();
                    let _ = child.wait();
                    log::info!("Đã tắt tiến trình backend.");
                }
            }
        });
}
