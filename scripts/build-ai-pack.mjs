// Builds the downloadable AI pack (ai-pack-win64.zip): a `pip install --target`
// directory with torch (CPU), demucs, speechbrain, faster-whisper, scikit-learn...
// The backend downloads it on first use (backend/app/core/packs.py) and adds it to
// sys.path, so it MUST be built with the same Python minor version as the
// PyInstaller backend (3.11). Output: dist-packs/ai-pack-win64.zip
//   node scripts/build-ai-pack.mjs
import { execFileSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, readdirSync, rmSync, statSync } from "node:fs";
import { join } from "node:path";
import { ROOT, resolvePython, assertPythonRuns } from "./python-path.mjs";

const python = resolvePython();
assertPythonRuns(python);

const stage = join(ROOT, "build", "ai-pack");
const outDir = join(ROOT, "dist-packs");
const zip = join(outDir, "ai-pack-win64.zip");

rmSync(stage, { recursive: true, force: true });
mkdirSync(stage, { recursive: true });
mkdirSync(outDir, { recursive: true });

console.log("Installing AI pack dependencies ...");
execFileSync(
  python,
  ["-m", "pip", "install", "--target", stage, "--no-compile", "--no-warn-script-location",
   "-r", join(ROOT, "backend", "requirements-ai.txt")],
  { stdio: "inherit" },
);

// Prune what is never needed at runtime: headers, import libs, console scripts, caches.
function walk(dir, visit) {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) {
      if (visit(full, name, true) !== false) walk(full, visit);
    } else {
      visit(full, name, false);
    }
  }
}
walk(stage, (full, name, isDir) => {
  if (isDir && (name === "__pycache__" || name === "include" || name === "bin")) {
    rmSync(full, { recursive: true, force: true });
    return false;
  }
  if (!isDir && /\.(lib|pyi|pdb|h|hpp|cmake)$/i.test(name)) rmSync(full, { force: true });
});

// torch_cpu.dll needs the VC++ 2022 runtime piece Windows does not ship.
const vc = join(process.env.SystemRoot ?? "C:\Windows", "System32", "vcruntime140_threads.dll");
if (!existsSync(vc)) throw new Error(`Missing ${vc}: install the Visual C++ 2022 Redistributable.`);
copyFileSync(vc, join(stage, "vcruntime140_threads.dll"));

console.log("Zipping ...");
rmSync(zip, { force: true });
// bsdtar (Windows 10+) writes zip with -a; call it by full path (Git Bash's tar is GNU tar).
execFileSync(join(process.env.SystemRoot ?? "C:\Windows", "System32", "tar.exe"),
  ["-a", "-c", "-f", zip, "-C", stage, "."], { stdio: "inherit" });
console.log(`Done: ${zip} (${(statSync(zip).size / 1e6).toFixed(0)} MB)`);
