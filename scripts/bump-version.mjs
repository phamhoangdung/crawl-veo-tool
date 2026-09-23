// Tăng version cho bản đóng gói. Nguồn chuẩn là src-tauri/tauri.conf.json (tên file
// installer lấy từ đó), rồi đồng bộ sang Cargo.toml và frontend/package.json.
//   node scripts/bump-version.mjs [patch|minor|major|x.y.z] [--dry]
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const args = process.argv.slice(2);
const dry = args.includes("--dry");
const target = args.find((a) => !a.startsWith("--")) ?? "patch";

const tauriConf = resolve(root, "src-tauri/tauri.conf.json");
const cargoToml = resolve(root, "src-tauri/Cargo.toml");
const frontendPkg = resolve(root, "frontend/package.json");

const SEMVER = /^(\d+)\.(\d+)\.(\d+)$/;
const VERSION_LINE = { json: /("version"\s*:\s*")([^"]+)(")/, toml: /^(version\s*=\s*")([^"]+)(")/m };

function readVersion(file, kind) {
  const m = readFileSync(file, "utf8").match(VERSION_LINE[kind]);
  if (!m) throw new Error(`Không tìm thấy version trong ${file}`);
  return m[2];
}

function next(current) {
  if (SEMVER.test(target)) return target;
  const m = current.match(SEMVER);
  if (!m) throw new Error(`Version hiện tại "${current}" không phải dạng x.y.z`);
  const [maj, min, pat] = m.slice(1).map(Number);
  if (target === "major") return `${maj + 1}.0.0`;
  if (target === "minor") return `${maj}.${min + 1}.0`;
  if (target === "patch") return `${maj}.${min}.${pat + 1}`;
  throw new Error(`Đối số không hợp lệ "${target}" — dùng patch | minor | major | x.y.z`);
}

function write(file, kind, version) {
  const text = readFileSync(file, "utf8");
  // Chỉ thay lần xuất hiện ĐẦU TIÊN: ở Cargo.toml đó là version của [package],
  // các dòng version của dependency nằm phía sau.
  writeFileSync(file, text.replace(VERSION_LINE[kind], `$1${version}$3`));
}

const current = readVersion(tauriConf, "json");
const version = next(current);
console.log(`Version: ${current} -> ${version}${dry ? " (dry-run, không ghi file)" : ""}`);

if (!dry) {
  write(tauriConf, "json", version);
  write(cargoToml, "toml", version);
  write(frontendPkg, "json", version);
}
