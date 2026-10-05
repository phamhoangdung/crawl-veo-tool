// Runs any Python command with the project's interpreter.
// Example: node scripts/run-python.mjs -m pytest backend
import { spawn } from "node:child_process";
import {
  ROOT,
  isWindows,
  resolvePython,
  assertPythonRuns,
  reportSpawnError,
} from "./python-path.mjs";

const python = resolvePython();
assertPythonRuns(python);
const args = process.argv.slice(2);

if (args.length === 0) {
  console.error("Dùng: node scripts/run-python.mjs <đối số truyền cho python>");
  process.exit(1);
}

const child = spawn(python, args, { cwd: ROOT, stdio: "inherit", shell: isWindows });

child.on("error", (err) => {
  reportSpawnError(err, python);
  process.exit(1);
});

// Forward Ctrl+C to the child process, then exit with its exit code.
for (const sig of ["SIGINT", "SIGTERM"]) {
  process.on(sig, () => child.kill(sig));
}

child.on("exit", (code, signal) => {
  process.exit(signal ? 1 : (code ?? 0));
});
