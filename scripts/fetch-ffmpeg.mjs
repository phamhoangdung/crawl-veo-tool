// Tải ffmpeg/ffprobe (bản "essentials" của gyan.dev, build tĩnh) về backend/vendor/ffmpeg
// để PyInstaller đóng gói cùng backend — máy người dùng không cần tự cài ffmpeg.
// Chạy 1 lần (bỏ qua nếu đã có); `--force` để tải lại.
import { execFileSync } from "node:child_process";
import { createWriteStream, existsSync, mkdirSync, rmSync, readdirSync, copyFileSync } from "node:fs";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { tmpdir } from "node:os";

// Bản phát hành cùng của gyan.dev nhưng host trên GitHub (gyan.dev tải rất chậm).
// Ghim phiên bản để mỗi lần build ra đúng cùng một ffmpeg.
const FFMPEG_VERSION = "9.0.2";
const URL = `https://github.com/GyanD/codexffmpeg/releases/download/${FFMPEG_VERSION}/ffmpeg-${FFMPEG_VERSION}-essentials_build.zip`;
const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const outDir = join(root, "backend", "vendor", "ffmpeg");
const force = process.argv.includes("--force");

if (!force && existsSync(join(outDir, "ffmpeg.exe")) && existsSync(join(outDir, "ffprobe.exe"))) {
  console.log(`ffmpeg đã có ở ${outDir} — bỏ qua (dùng --force để tải lại).`);
  process.exit(0);
}

const work = join(tmpdir(), `viedub-ffmpeg-${Date.now()}`);
mkdirSync(work, { recursive: true });
const zip = join(work, "ffmpeg.zip");

console.log(`Đang tải ${URL} ...`);
const res = await fetch(URL);
if (!res.ok || !res.body) throw new Error(`Tải ffmpeg thất bại: HTTP ${res.status}`);
await pipeline(Readable.fromWeb(res.body), createWriteStream(zip));

console.log("Đang giải nén ...");
// bsdtar của Windows 10+ đọc được .zip (gọi đủ đường dẫn: `tar` của Git Bash là GNU tar, hiểu nhầm "C:" là máy từ xa)
execFileSync(join(process.env.SystemRoot ?? "C:\\Windows", "System32", "tar.exe"), ["-xf", zip, "-C", work], { stdio: "inherit" });

const extracted = readdirSync(work).find((n) => n.startsWith("ffmpeg-") && !n.endsWith(".zip"));
if (!extracted) throw new Error("Không thấy thư mục ffmpeg-* sau khi giải nén.");

rmSync(outDir, { recursive: true, force: true });
mkdirSync(outDir, { recursive: true });
for (const name of ["ffmpeg.exe", "ffprobe.exe"]) {
  copyFileSync(join(work, extracted, "bin", name), join(outDir, name));
}
// Bản GPL: giấy phép + README phải đi kèm khi phát hành lại.
for (const name of ["LICENSE", "README.txt"]) {
  const src = join(work, extracted, name);
  if (existsSync(src)) copyFileSync(src, join(outDir, name));
}
rmSync(work, { recursive: true, force: true });
console.log(`Xong: ${outDir}`);
