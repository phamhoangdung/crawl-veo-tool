// Chạy uvicorn bằng interpreter phù hợp với máy đang chạy (xem python-path.mjs).
import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import {
  ROOT,
  isWindows,
  resolvePython,
  assertPythonRuns,
  reportSpawnError,
} from "./python-path.mjs";

// Cổng lấy từ .env ở root (nguồn duy nhất), env của shell được ưu tiên cao hơn.
function backendPortFromEnvFile() {
  const envPath = resolve(ROOT, ".env");
  if (!existsSync(envPath)) return undefined;
  for (const line of readFileSync(envPath, "utf-8").split("\n")) {
    const match = line.trim().match(/^BACKEND_PORT\s*=\s*(.+)$/);
    if (match) return match[1].trim();
  }
  return undefined;
}

const python = resolvePython();
const version = assertPythonRuns(python);
const port = process.env.BACKEND_PORT ?? backendPortFromEnvFile() ?? "8000";
const args = ["-m", "uvicorn", "app.main:app", "--reload", "--app-dir", "backend", "--port", port];

console.log(`[backend] ${python} (${version}) :${port}`);

const child = spawn(python, args, {
  cwd: ROOT,
  stdio: "inherit",
  // Trên Windows, đường dẫn .exe cần shell để cmd giải đúng.
  shell: isWindows,
});

child.on("error", (err) => {
  reportSpawnError(err, python);
  process.exit(1);
});

// Chuyển tiếp Ctrl+C xuống uvicorn rồi thoát theo đúng exit code của nó.
for (const sig of ["SIGINT", "SIGTERM"]) {
  process.on(sig, () => child.kill(sig));
}

child.on("exit", (code, signal) => {
  process.exit(signal ? 1 : (code ?? 0));
});
