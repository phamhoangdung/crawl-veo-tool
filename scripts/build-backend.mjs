// Builds the PyInstaller backend sidecar (backend/dist/viedub-backend) with whichever
// Python the project resolves (backend/.venv on Windows and macOS alike).
//   node scripts/build-backend.mjs
import { spawnSync } from "node:child_process";
import { join } from "node:path";
import { ROOT, resolvePython, assertPythonRuns } from "./python-path.mjs";

const python = resolvePython();
assertPythonRuns(python);

const result = spawnSync(
  python,
  ["-m", "PyInstaller", "--distpath", "dist", "--workpath", "build", "--noconfirm", "viedub-backend.spec"],
  { cwd: join(ROOT, "backend"), stdio: "inherit" },
);
process.exit(result.status ?? 1);
