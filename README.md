# Crawl Video Tool

A personal tool that runs locally: enter a keyword/topic → crawl and download videos from **Bilibili** (Douyin is work in progress) → **translate and dub with AI** (Chinese → Vietnamese) → export the video with **bilingual subtitles**, keeping the original background music.

- **Backend**: Python 3.11+ / FastAPI / SQLAlchemy + SQLite (WAL), served on `:8000`
- **Frontend**: React + Vite + TypeScript + Tailwind + shadcn/ui, served on `:5173`
- **Media processing**: ffmpeg, faster-whisper (STT), demucs (background-music separation), edge-tts / ElevenLabs (TTS), OpenAI / Google (translation)
- **Desktop app**: Tauri shell + PyInstaller backend sidecar, shipped as a Windows installer (see [Desktop installer](#9-desktop-installer))

> Detailed architecture and roadmap: [docs/overview/plan.md](docs/overview/plan.md) · Per-phase progress: [docs/phases/](docs/phases/) · Coding conventions: [docs/conventions.md](docs/conventions.md)

> Note: the app UI and the project docs under `docs/` are written in Vietnamese. Code comments are in English.

## About VieDub Studio

VieDub Studio turns foreign-language short videos into Vietnamese-dubbed videos with a few clicks, entirely on your own machine. Your videos, transcripts and API keys never leave your computer, except for calls you choose to make to AI providers.

**What it does**

- **Discover and download**: browse Bilibili trends or search by keyword, preview videos, select many at once and download them without watermark (multi-connection downloads for speed). Follow channels to find related videos.
- **Transcribe**: speech-to-text with faster-whisper, with an editable transcript and optional speaker separation for multi-voice videos.
- **Translate**: Chinese to Vietnamese through the AI provider you choose (OpenAI, Google, DeepL, ...). You bring your own API keys.
- **Dub**: text-to-speech (Edge-TTS, ElevenLabs, ...) mixed over the video while **keeping the original background music** (separated with Demucs).
- **Subtitles**: bilingual `.srt` (original + translation), with an option to burn them into the video.
- **Edit and export**: timeline editor, short-clip cutting, library with single or `.zip` bulk download.

---

## Quick install (end users, Windows)

1. Open the **Releases** page of this repository and download the latest `VieDub Studio_x.y.z_x64-setup.exe`.
2. Run it. It installs per user (no administrator rights needed). Windows SmartScreen may warn because the installer is not code-signed: click **More info → Run anyway**.
3. Start **VieDub Studio** from the Start menu. The installer is small on purpose: heavy components are downloaded once, on demand. A banner at the top of the app offers **ffmpeg** (~110MB) and the **AI pack** (Whisper, Demucs, speaker separation; ~250MB download, ~800MB on disk). Click **Tải về** on each and wait for it to finish; this needs an internet connection.
4. Open the **API Keys** page and enter the keys of the AI providers you want to use (translation / TTS). Keys are encrypted and stored locally.
5. On the first transcription/dubbing run the app also downloads the speech models (Whisper ~460MB, Demucs ~80MB). This happens only once.

Where things live: user data and settings in `%APPDATA%\VieDubStudio`, backend log in `%APPDATA%\VieDubStudio\logs\backend.log` (also viewable in the app via the avatar menu → **System logs**). To uninstall, use Windows **Apps → Installed apps**; delete `%APPDATA%\VieDubStudio` as well if you want to remove your data.

Developers who want to run from source should continue with the sections below.

---

## 1. Requirements

| Tool | Notes |
|---|---|
| **Python 3.11+** | Use `python3` (on Windows a bare `python` may point to the Microsoft Store stub) |
| **Node.js + npm** | Only used at the repo root to orchestrate the two services |
| **pnpm** | `npm install -g pnpm`. `frontend/` uses `pnpm-lock.yaml`; do **not** use npm inside `frontend/` |
| **ffmpeg** | Required and must be on PATH. Windows: `winget install --id Gyan.FFmpeg -e` · macOS: `brew install ffmpeg` · Linux: `apt install ffmpeg` |
| **git** | |

After installing ffmpeg on Windows, **close and reopen your terminal/VSCode**. The new PATH only applies to sessions opened afterwards.

## 2. Installation

### 2.1. Automatic (recommended, works on all 3 OSes)

```bash
npm install     # installs concurrently for the root
npm run setup   # creates the venv, installs backend and frontend deps, creates .env
```

[scripts/setup.mjs](scripts/setup.mjs) finds Python on PATH, creates `backend/.venv`, installs `requirements.txt`, runs `pnpm install` for the frontend, creates `.env` from `.env.example`, and warns if ffmpeg is missing.

To install straight into the **global Python** (no venv):

```bash
NO_VENV=1 npm run setup          # macOS / Linux
set NO_VENV=1 && npm run setup   # Windows cmd
$env:NO_VENV=1; npm run setup    # Windows PowerShell
```

Installing `faster-whisper` + `demucs` pulls in PyTorch (~2GB), so the first run can take 5–15 minutes depending on your connection.

### 2.2. Manual

```bash
cd backend
python3 -m venv .venv

# Windows
.venv\Scripts\python.exe -m pip install -r requirements.txt

# macOS / Linux
.venv/bin/python -m pip install -r requirements.txt

cd ../frontend && pnpm install
```

The first pipeline run downloads extra models (network required, may be slow):
`faster-whisper` (a few hundred MB) and `demucs / htdemucs` (~80MB).

### 2.3. Environment variables

There is a **single** source `.env` at the repo root (`npm run setup` creates it; for a manual install run `cp .env.example .env`).

Open `.env` and fill in `MASTER_KEY`, the key used to encrypt provider API keys stored in the DB. Generate a new value:

```bash
python3 -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

| Variable | Required | Default |
|---|---|---|
| `MASTER_KEY` | yes | none |
| `BACKEND_PORT` | | `8000` |
| `FRONTEND_PORT` | | `5173` |
| `DATABASE_URL` | | `sqlite:///backend/storage/app.db` |

`backend/.env` and `frontend/.env` are **generated automatically** from this file every time you run `npm run dev` ([scripts/sync-env.mjs](scripts/sync-env.mjs)). Do not edit those two files by hand.

AI provider API keys (OpenAI, Google, ElevenLabs, ...) do **not** go in `.env`. Enter them in the UI on the **API Keys** page; the tool encrypts them with `MASTER_KEY` and stores them in the DB.

## 3. Running the project

```bash
npm run dev    # runs backend (:8000) and frontend (:5173) together
```

Open http://localhost:5173. The command behaves the same on Windows, macOS and Linux.

**Which Python does the backend use?** [scripts/run-backend.mjs](scripts/run-backend.mjs) looks, in order, at:

1. The `PYTHON` environment variable, e.g. `PYTHON=/path/to/python npm run dev`
2. `backend/.venv`, picking `Scripts/python.exe` (Windows) or `bin/python` (macOS/Linux)
3. The global Python on PATH: `python` on Windows, `python3` on macOS/Linux

This way the project works with a venv or with the global Python without editing `package.json`.

### Checking that it works

```bash
curl http://localhost:8000/health              # backend is alive
curl http://localhost:8000/health/downloader   # Bilibili API still behaves as the code assumes
```

Swagger API docs are served at http://localhost:8000/docs.

## 4. Usage flow

1. **Trending / Crawl**: pick a topic or enter a keyword and the tool lists videos from Bilibili (with an estimated AI cost preview before running).
2. **Download**: fetch the original video without watermark.
3. **Transcribe**: faster-whisper extracts the Chinese speech with timestamps (the transcript can be edited by hand in the UI).
4. **Translate**: translate to Vietnamese with the selected provider.
5. **Dub**: demucs separates the voice from the background music, TTS reads the translation, and the result is mixed back **keeping the original background music** (with time-stretching to match timing).
6. **Subtitles**: export bilingual `.srt`, optionally burned into the video.
7. **Library**: review videos, download one at a time or in bulk as a `.zip`.

## 5. Project layout

```
backend/
  app/
    api/          # FastAPI routers (health, crawl, trending, api_keys, pipeline, library)
    services/     # business logic (download, transcribe, translate, tts, dubbing, subtitle, cost...)
    adapters/     # external integrations: bilibili, douyin, translate/*, tts/*, ffmpeg, demucs
    models/       # SQLAlchemy models
    schemas/      # Pydantic schemas
    core/         # config, db, security (API key encryption)
  storage/        # DB + generated media files (gitignored)
frontend/
  src/
    features/     # crawl, trending, library, api-keys, settings, dashboard...
    routes/       # TanStack Router (file-based)
    components/   # shared shadcn/ui + layout
src-tauri/        # Tauri desktop shell
scripts/          # dev/build helper scripts (setup, sync-env, run-backend, fetch-ffmpeg, bump-version)
docs/
  overview/plan.md   # overall architecture
  phases/            # execution checklist per phase
  conventions.md     # coding conventions
```

## 6. Main API

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health`, `/health/downloader` | Health checks |
| `GET` | `/api/trending/bilibili/categories\|popular\|ranking` | Trending discovery |
| `POST` | `/api/jobs` | Create a crawl job |
| `POST` | `/api/jobs/{job_id}/cost-estimate` | Estimate AI cost |
| `GET/PUT` | `/api/api-keys` | Manage provider API keys |
| `GET` | `/api/videos/{id}` | Video details |
| `POST` | `/api/videos/{id}/download\|transcribe\|translate\|dub\|burn-subtitles` | Pipeline steps |
| `PUT` | `/api/videos/{id}/transcript` | Edit the transcript manually |
| `GET` | `/api/videos/{id}/subtitles.srt` | Download subtitles |
| `GET` | `/api/library`, `/api/library/{id}/download`, `/api/library/download-zip` | Library and downloads |

## 7. Tests and lint

```bash
npm test               # runs backend (pytest) and frontend (vitest)
npm run test:backend   # backend only, finds Python the same way as dev
npm run test:frontend  # frontend only

pnpm -C frontend lint
pnpm -C frontend format
```

To run any Python command with the project's own interpreter:

```bash
node scripts/run-python.mjs -m pytest backend/tests/test_subtitle.py
```

## 8. Troubleshooting

- **`ffmpeg: command not found` even after installing** → PATH is only updated for new terminals; close and reopen the terminal/VSCode.
- **`WinError 10013` on `npm run dev`** → port 8000 is still held by an old process (uvicorn `--reload` does not fully replace the worker). Find and kill it:
  ```powershell
  Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'multiprocessing-fork' }
  Stop-Process -Id <id> -Force
  ```
- **`UNIQUE constraint failed` / `no such column` after changing a model** → the MVP does not use Alembic, so the schema does not auto-migrate. Delete `backend/storage/app.db*` to let SQLAlchemy recreate it (old test data is lost), or run `ALTER TABLE` manually.
- **CORS blocked** → Vite jumps to another port (5174, 5175, ...) if 5173 is busy. The backend already accepts any `localhost` port; if it still fails, check `CORSMiddleware` in [backend/app/main.py](backend/app/main.py).
- **The first pipeline run is very slow** → the faster-whisper / demucs models are being downloaded; it is slow only once.
- **`npm run setup` / `npm run dev` hangs without output** → the Python on PATH is broken (even `python3 --version` hangs). The scripts time out after 10s and report an error, but the fix is to reinstall Python and point to the new one:
  ```bash
  python3 --version          # if this hangs, Python is broken
  brew reinstall python@3.12 # macOS
  PYTHON=python3.12 npm run setup
  ```
- **pip fails installing `demucs` / `faster-whisper`** → PyTorch does not support your Python version yet (common with 3.13+). Use Python 3.11 or 3.12: `PYTHON=python3.12 npm run setup`.

Detailed Windows-specific setup guide: [SETUP.md](SETUP.md).

## 9. Desktop installer

The app can be packaged as a Windows installer (Tauri + a slim PyInstaller-built backend sidecar; ffmpeg and the AI libraries are downloaded on first use as "packs").

```bash
npm run desktop:build        # bumps the patch version, then builds the installer
npm run desktop:build:keep   # builds without bumping the version
npm run desktop:build-ai-pack # builds dist-packs/ai-pack-win64.zip (the downloadable AI pack)
```

The installer is written to `src-tauri/target/release/bundle/nsis/`. Run the build from PowerShell/cmd, not Git Bash (Git Bash shadows MSVC's `link.exe`). User data lives in `%APPDATA%\VieDubStudio`, and the backend log is at `%APPDATA%\VieDubStudio\logs\backend.log`. Details: [docs/phases/phase-12-desktop-packaging.md](docs/phases/phase-12-desktop-packaging.md).

**Publishing a release:** pushing a tag such as `v0.1.9` triggers [.github/workflows/release.yml](.github/workflows/release.yml), which builds the installer on a Windows runner and attaches the `.exe` to a GitHub Release. The tag must match the version in `src-tauri/tauri.conf.json`. The AI pack is published separately by the manual **ai-pack** workflow (release `ai-pack-v<AI_PACK_VERSION>`, see `backend/app/core/packs.py`); run it once before the first app release and again only when `backend/requirements-ai.txt` changes. You can also run the release workflow manually from the Actions tab (build only, no Release). The installer is unsigned, so Windows SmartScreen will show a warning.

## 10. Status

See the phase table in [CLAUDE.md](CLAUDE.md) for the up-to-date status of every phase and the per-phase files under [docs/phases/](docs/phases/) for details. Summary:

| Phase | Status |
|---|---|
| 0. Scaffolding | Done |
| 1. Crawl and trending (Bilibili) | Done (except batch queue concurrency) |
| 2. AI pipeline MVP | Done, verified end to end |
| 3. Multi-provider + Douyin | Partial: cost estimate done, Douyin blocked (no account) |
| 4. Audio quality (background music separation) | Done and verified |
| 5. Bilingual subtitles + Library | Done and verified |
| 6. Hardening and ops | Done and verified |
| 12. Desktop packaging | Real installer built; not yet run on a separate clean machine |
| 19. Multi-speaker dubbing | Core code done; not yet verified on real video/GPU |
| 20-22. Discovery workspace, parallel download, channel follow | Done and verified |

This is a personal-use tool with no real user authentication. **Do not expose it to the internet.**
