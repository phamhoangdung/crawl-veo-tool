// Nguồn duy nhất quyết định dùng interpreter Python nào — dùng chung cho
// run-backend.mjs và run-python.mjs.
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
export const isWindows = process.platform === "win32";

/**
 * Các bản Python được dự án hỗ trợ, ưu tiên từ trái sang. Chỉ 3.11/3.12 vì
 * PyTorch (demucs, faster-whisper phụ thuộc) chưa có bản build cho 3.13+.
 * Ưu tiên tên có số phiên bản để không dính phải `python3` mặc định của hệ
 * thống — vốn có thể quá cũ hoặc đang hỏng.
 */
export const SUPPORTED_PYTHONS = isWindows
  ? ["python3.12", "python3.11", "python", "python3"]
  : ["python3.12", "python3.11", "python3", "python"];

/** Interpreter chạy được không? Có timeout vì bản cài hỏng có thể treo vô hạn. */
function runs(cmd) {
  const res = spawnSync(cmd, ["--version"], { stdio: "ignore", timeout: 5000 });
  return !res.error && res.status === 0;
}

/**
 * Thứ tự ưu tiên: biến PYTHON → backend/.venv → bản đầu tiên trong
 * SUPPORTED_PYTHONS thực sự chạy được.
 */
export function resolvePython() {
  if (process.env.PYTHON) return process.env.PYTHON;

  const venvPython = isWindows
    ? resolve(ROOT, "backend/.venv/Scripts/python.exe")
    : resolve(ROOT, "backend/.venv/bin/python");
  if (existsSync(venvPython)) return venvPython;

  // Bỏ qua bản treo/hỏng thay vì để nó làm đứng cả lệnh.
  return SUPPORTED_PYTHONS.find(runs) ?? (isWindows ? "python" : "python3");
}

/**
 * Kiểm tra interpreter thực sự chạy được trước khi giao việc dài cho nó.
 * Có timeout vì một bản Python cài hỏng có thể treo vô hạn thay vì báo lỗi —
 * để mặc thì `npm run dev` sẽ đứng im không rõ lý do.
 */
export function assertPythonRuns(python) {
  const res = spawnSync(python, ["--version"], {
    encoding: "utf-8",
    timeout: 10000,
  });

  if (res.error?.code === "ENOENT") {
    console.error(
      `\n✗ Không tìm thấy Python (\`${python}\`).\n` +
        `  → Chạy \`npm run setup\`, hoặc chỉ định: PYTHON=/đường/dẫn/python npm run dev\n`
    );
    process.exit(1);
  }

  if (res.error?.code === "ETIMEDOUT" || res.signal === "SIGTERM") {
    console.error(
      `\n✗ \`${python} --version\` bị treo quá 10s — bản Python này hỏng.\n` +
        `  Kiểm tra bằng tay: ${python} --version\n` +
        `  macOS: thử cài lại \`brew reinstall python@3.12\` rồi chạy\n` +
        `         PYTHON=python3.12 npm run dev\n`
    );
    process.exit(1);
  }

  if (res.status !== 0) {
    console.error(
      `\n✗ \`${python} --version\` lỗi (exit ${res.status}).\n` +
        `${(res.stderr || "").trim()}\n`
    );
    process.exit(1);
  }

  return (res.stdout || res.stderr || "").trim();
}

export function reportSpawnError(err, python) {
  if (err.code === "ENOENT") {
    console.error(
      `\n✗ Không tìm thấy Python (\`${python}\`).\n` +
        `  → Chạy \`npm run setup\` để tạo venv và cài phụ thuộc, hoặc\n` +
        `  → Chỉ định thủ công: PYTHON=/đường/dẫn/python npm run dev\n`
    );
  } else {
    console.error(`✗ ${err.message}`);
  }
}
