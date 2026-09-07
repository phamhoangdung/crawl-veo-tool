// Cài đặt phụ thuộc cho cả backend lẫn frontend, chạy được trên
// Windows/macOS/Linux. Dùng: `npm run setup`.
import { spawnSync } from "node:child_process";
import { copyFileSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { SUPPORTED_PYTHONS } from "./python-path.mjs";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const isWindows = process.platform === "win32";
const USE_VENV = process.env.NO_VENV !== "1";

function run(cmd, args, opts = {}) {
  console.log(`\n$ ${cmd} ${args.join(" ")}`);
  const res = spawnSync(cmd, args, {
    cwd: ROOT,
    stdio: "inherit",
    shell: isWindows,
    ...opts,
  });
  if (res.error?.code === "ENOENT") fail(`Không tìm thấy lệnh \`${cmd}\`.`);
  if (res.status !== 0) fail(`Lệnh \`${cmd}\` thất bại (exit ${res.status}).`);
}

function fail(msg) {
  console.error(`\n✗ ${msg}`);
  process.exit(1);
}

function which(cmd) {
  const res = spawnSync(isWindows ? "where" : "which", [cmd], {
    stdio: "ignore",
    shell: isWindows,
    timeout: 5000,
  });
  return res.status === 0;
}

/**
 * Hỏi `--version` để chắc chắn interpreter thực sự chạy được. Có timeout vì
 * một bản Python cài hỏng có thể treo vô hạn thay vì báo lỗi.
 */
function probePython(cmd) {
  const res = spawnSync(cmd, ["--version"], {
    encoding: "utf-8",
    timeout: 10000,
  });
  if (res.error || res.status !== 0) return null;
  return (res.stdout || res.stderr || "").trim();
}

// 1. Tìm Python global để tạo venv / cài thẳng.
console.log("Đang tìm Python khả dụng...");
const candidates = process.env.PYTHON ? [process.env.PYTHON] : SUPPORTED_PYTHONS;

let basePython = null;
let pythonVersion = null;
for (const cmd of candidates) {
  if (!process.env.PYTHON && !which(cmd)) continue;
  const version = probePython(cmd);
  if (version) {
    basePython = cmd;
    pythonVersion = version;
    break;
  }
  console.warn(`  ⚠ \`${cmd}\` có trong PATH nhưng không chạy được (treo hoặc lỗi) — bỏ qua.`);
}

if (!basePython) {
  fail(
    "Không tìm thấy Python chạy được. Cài Python 3.11–3.12 rồi chạy lại.\n" +
      "  Windows: winget install -e --id Python.Python.3.12\n" +
      "  macOS:   brew install python@3.12\n" +
      "  Linux:   sudo apt install python3 python3-venv python3-pip\n" +
      "Hoặc trỏ thẳng tới bản đang có: PYTHON=/đường/dẫn/python npm run setup"
  );
}

console.log(`Python: ${basePython} (${pythonVersion})`);

// PyTorch (demucs/faster-whisper phụ thuộc) thường chưa có bản build cho các
// phiên bản Python quá mới — cảnh báo sớm thay vì để pip lỗi khó hiểu.
const minor = Number(pythonVersion.match(/^Python 3\.(\d+)/)?.[1]);
if (Number.isFinite(minor) && (minor < 11 || minor > 12)) {
  console.warn(
    `\n⚠ Dự án cần Python 3.11–3.12; đang dùng 3.${minor}.\n` +
      "  PyTorch (demucs, faster-whisper) có thể chưa hỗ trợ phiên bản này.\n" +
      "  Nếu pip lỗi, cài bản phù hợp rồi chạy: PYTHON=python3.12 npm run setup\n"
  );
}

// 2. Backend deps.
const venvDir = resolve(ROOT, "backend/.venv");
const venvPython = isWindows
  ? resolve(venvDir, "Scripts/python.exe")
  : resolve(venvDir, "bin/python");

let backendPython = basePython;
if (USE_VENV) {
  if (!existsSync(venvPython)) run(basePython, ["-m", "venv", "backend/.venv"]);
  backendPython = venvPython;
} else {
  console.log("NO_VENV=1 → cài thẳng vào Python global.");
}

run(backendPython, ["-m", "pip", "install", "--upgrade", "pip"]);

console.log(
  "\nCài phụ thuộc backend — bước này kéo theo PyTorch (~2GB) nên lần đầu\n" +
    "có thể mất 5–15 phút tuỳ tốc độ mạng. Cứ để chạy."
);
run(backendPython, ["-m", "pip", "install", "-r", "backend/requirements.txt"]);

// 3. Frontend deps.
if (!which("pnpm")) fail("Chưa có pnpm. Cài bằng: npm install -g pnpm");
run("pnpm", ["-C", "frontend", "install"]);

// 4. File .env ở root.
const envPath = resolve(ROOT, ".env");
if (!existsSync(envPath)) {
  copyFileSync(resolve(ROOT, ".env.example"), envPath);
  console.log("\nĐã tạo .env từ .env.example.");
}

// 5. Cảnh báo ffmpeg (bắt buộc cho pipeline, không tự cài được).
if (!which("ffmpeg")) {
  console.warn(
    "\n⚠ Không tìm thấy ffmpeg — pipeline sẽ lỗi khi xử lý video. Cài bằng:\n" +
      "  Windows: winget install -e --id Gyan.FFmpeg  (rồi mở lại terminal)\n" +
      "  macOS:   brew install ffmpeg\n" +
      "  Linux:   sudo apt install ffmpeg"
  );
}

console.log(
  "\n✓ Xong. Việc còn lại:\n" +
    "  1. Điền MASTER_KEY trong .env — sinh giá trị:\n" +
    `     ${basePython} -c "import secrets,base64;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"\n` +
    "  2. npm run dev"
);
