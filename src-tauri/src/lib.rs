use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;

use tauri::{Manager, RunEvent};

/// Giữ tiến trình backend đã spawn để tắt sạch khi đóng app — không tắt sẽ để lại
/// tiến trình Python treo lại (xem docs/phases/phase-12-desktop-packaging.md, mục
/// "Tiêu chí hoàn thành": phải kiểm tra Task Manager không còn tiến trình orphan).
struct BackendProcess(Mutex<Option<Child>>);

/// Đường dẫn tới `viedub-backend.exe` — dev mode trỏ thẳng vào thư mục build của
/// PyInstaller (`backend/dist/viedub-backend/`, tương đối theo CWD lúc `tauri dev`
/// chạy là `src-tauri/`), bản đóng gói dùng resource đã bundle theo
/// `tauri.conf.json` (`bundle.resources`).
fn resolve_backend_exe(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    if cfg!(debug_assertions) {
        let dev_path = PathBuf::from("../backend/dist/viedub-backend/viedub-backend.exe");
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
    Ok(resource_dir.join("backend").join("viedub-backend.exe"))
}

/// Cổng backend lắng nghe. Bản đóng gói xin hệ điều hành 1 cổng đang RẢNH thay vì
/// cố định 8000 — máy người dùng có thể đã có phần mềm khác (hoặc bản app cũ chưa
/// tắt hẳn) chiếm 8000, khi đó giao diện sẽ nói chuyện nhầm với tiến trình lạ.
/// Dev mode giữ 8000 vì frontend dev (Vite) trỏ cứng vào đó.
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
    // Nhật ký backend tự ghi ra file (xem backend/app/core/logging_setup.py), nên
    // không cần console: null handle để Python vẫn có stdout/stderr hợp lệ.
    command
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    // Không có cờ này Windows mở cửa sổ cmd cho mỗi sidecar console.
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

            // Cửa sổ tạo ở đây (không để tauri.conf.json tự tạo) để tiêm được địa chỉ
            // backend vào trang TRƯỚC khi frontend chạy — `frontend/src/lib/api.ts` đọc
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
            // Tắt sạch tiến trình backend khi app đóng — tránh treo lại tiến trình
            // Python nền (xem DoD ở docs/phases/phase-12-desktop-packaging.md).
            if let RunEvent::Exit = event {
                let state = app_handle.state::<BackendProcess>();
                // Lấy Child ra khỏi Mutex rồi nhả lock ngay (không giữ lock trong
                // lúc kill/wait — đó là I/O chặn, không nên giữ mutex khi làm việc đó).
                let child_opt = state.0.lock().unwrap().take();
                if let Some(mut child) = child_opt {
                    let _ = child.kill();
                    let _ = child.wait();
                    log::info!("Đã tắt tiến trình backend.");
                }
            }
        });
}
