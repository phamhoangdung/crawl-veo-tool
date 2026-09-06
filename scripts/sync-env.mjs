// Nguồn duy nhất là .env ở root. Script này copy đúng biến cần thiết vào
// backend/.env và frontend/.env trước mỗi lần `npm run dev` (xem "predev").
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");

function parseEnvFile(path) {
  if (!existsSync(path)) return {};
  const values = {};
  for (const line of readFileSync(path, "utf-8").split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq === -1) continue;
    values[trimmed.slice(0, eq).trim()] = trimmed.slice(eq + 1).trim();
  }
  return values;
}

const root = parseEnvFile(resolve(ROOT, ".env"));

if (!root.MASTER_KEY) {
  console.error("Thiếu MASTER_KEY trong .env ở root — copy .env.example thành .env và điền giá trị trước.");
  process.exit(1);
}

const backendPort = root.BACKEND_PORT ?? "8000";

const backendEnv = [`MASTER_KEY=${root.MASTER_KEY}`];
if (root.DATABASE_URL) backendEnv.push(`DATABASE_URL=${root.DATABASE_URL}`);
writeFileSync(resolve(ROOT, "backend/.env"), backendEnv.join("\n") + "\n");

const frontendEnv = [`VITE_API_BASE_URL=http://localhost:${backendPort}`];
writeFileSync(resolve(ROOT, "frontend/.env"), frontendEnv.join("\n") + "\n");

console.log("Đã đồng bộ .env vào backend/.env và frontend/.env");
