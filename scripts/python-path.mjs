// Single source deciding which Python interpreter to use, shared by
// run-backend.mjs and run-python.mjs.
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
export const isWindows = process.platform === "win32";

/**
  * Python versions supported by the project, preferred first. Only 3.11/3.12 because
  * PyTorch (a dependency of demucs, faster-whisper) has no build for 3.13+ yet.
  * Prefer names with a version number so we do not pick the system default `python3`,
  * which may be too old or broken.
 */
export const SUPPORTED_PYTHONS = isWindows
  ? ["python3.12", "python3.11", "python", "python3"]
  : ["python3.12", "python3.11", "python3", "python"];

/** Does the interpreter run? Has a timeout because a broken install can hang forever. */
function runs(cmd) {
  const res = spawnSync(cmd, ["--version"], { stdio: "ignore", timeout: 5000 });
  return !res.error && res.status === 0;
}

/**
  * Priority order: the PYTHON variable → backend/.venv → the first entry of
  * SUPPORTED_PYTHONS that actually runs.
 */
export function resolvePython() {
  if (process.env.PYTHON) return process.env.PYTHON;

  const venvPython = isWindows
    ? resolve(ROOT, "backend/.venv/Scripts/python.exe")
    : resolve(ROOT, "backend/.venv/bin/python");
  if (existsSync(venvPython)) return venvPython;

  // Skip a hanging/broken interpreter instead of letting it block the whole command.
  return SUPPORTED_PYTHONS.find(runs) ?? (isWindows ? "python" : "python3");
}

/**
  * Check that the interpreter really runs before handing it a long job.
  * Has a timeout because a broken Python install can hang forever instead of reporting
  * an error; left alone, `npm run dev` would sit silent for no visible reason.
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
