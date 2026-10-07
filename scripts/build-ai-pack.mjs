// Builds the downloadable AI pack (ai-pack-win64.zip on Windows, ai-pack-macos-<arm64|x64>.tar.gz
// on macOS): a `pip install --target`
// directory with torch (CPU), demucs, speechbrain, faster-whisper, scikit-learn...
// The backend downloads it on first use (backend/app/core/packs.py) and adds it to
// sys.path, so it MUST be built with the same Python minor version as the
// PyInstaller backend (3.11). Output: dist-packs/<asset name>
//   node scripts/build-ai-pack.mjs
import { execFileSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, readdirSync, rmSync, statSync } from "node:fs";
import { join } from "node:path";
import { ROOT, isWindows, resolvePython, assertPythonRuns } from "./python-path.mjs";

const python = resolvePython();
assertPythonRuns(python);

const stage = join(ROOT, "build", "ai-pack");
const outDir = join(ROOT, "dist-packs");
// Intel Macs need an older, separately pinned set (PyTorch has no x86_64 macOS wheels > 2.2).
const intelMac = process.platform === "darwin" && process.arch === "x64";
const requirements = intelMac ? "requirements-ai-macos-intel.txt" : "requirements-ai.txt";
const assetName = isWindows
  ? "ai-pack-win64.zip"
  : intelMac ? "ai-pack-macos-x64.tar.gz" : "ai-pack-macos-arm64.tar.gz";
const zip = join(outDir, assetName);

rmSync(stage, { recursive: true, force: true });
mkdirSync(stage, { recursive: true });
mkdirSync(outDir, { recursive: true });

console.log("Installing AI pack dependencies ...");
execFileSync(
  python,
  ["-m", "pip", "install", "--target", stage, "--no-compile", "--no-warn-script-location",
   "-r", join(ROOT, "backend", requirements)],
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

if (isWindows) {
  // torch_cpu.dll needs the VC++ 2022 runtime piece Windows does not ship.
  const vc = join(process.env.SystemRoot ?? "C:\Windows", "System32", "vcruntime140_threads.dll");
  if (!existsSync(vc)) throw new Error(`Missing ${vc}: install the Visual C++ 2022 Redistributable.`);
  copyFileSync(vc, join(stage, "vcruntime140_threads.dll"));
}

console.log("Archiving ...");
rmSync(zip, { force: true });
if (isWindows) {
  // bsdtar (Windows 10+) writes zip with -a; call it by full path (Git Bash's tar is GNU tar).
  execFileSync(join(process.env.SystemRoot ?? "C:\Windows", "System32", "tar.exe"),
    ["-a", "-c", "-f", zip, "-C", stage, "."], { stdio: "inherit" });
} else {
  // tar.gz keeps symlinks and permission bits, which a zip would lose.
  execFileSync("tar", ["-czf", zip, "-C", stage, "."], { stdio: "inherit" });
}
console.log(`Done: ${zip} (${(statSync(zip).size / 1e6).toFixed(0)} MB)`);
