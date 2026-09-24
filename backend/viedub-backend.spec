# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

# Demucs không được import trực tiếp ở đâu trong app (chạy qua cờ --run-demucs của
# entrypoint), nên PyInstaller không tự thấy — phải gom tay cả code lẫn file cấu hình
# model (demucs/remote/*.yaml). SpeechBrain nạp module động qua hyperpyyaml.
extra_datas, extra_binaries, extra_hidden = [], [], []
for pkg in ('demucs', 'speechbrain', 'faster_whisper'):  # faster_whisper: file VAD silero .onnx
    d, b, h = collect_all(pkg)
    extra_datas += d
    extra_binaries += b
    extra_hidden += h

# torch_cpu.dll cần vcruntime140_threads.dll (VC++ 2022 Redistributable). PyInstaller
# không tự gom file này và Windows không có sẵn -> máy chưa cài VC++ sẽ lỗi khi
# nạp torch (phân vai người nói, Demucs). Kèm theo app (app-local, được phép).
import os
_vc_threads = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'vcruntime140_threads.dll'
if not _vc_threads.is_file():
    raise SystemExit(f'Thiếu {_vc_threads} — cài Visual C++ Redistributable 2022 trên máy build.')
extra_binaries.append((str(_vc_threads), '.'))

# ffmpeg/ffprobe đóng gói kèm để máy người dùng không cần tự cài. Chạy
# `npm run desktop:fetch-ffmpeg` để có thư mục này (không commit vào git).
ffmpeg_dir = Path('vendor/ffmpeg')
if not (ffmpeg_dir / 'ffmpeg.exe').is_file():
    raise SystemExit('Thiếu backend/vendor/ffmpeg — chạy: npm run desktop:fetch-ffmpeg')

a = Analysis(
    ['app/entrypoint.py'],
    pathex=[],
    binaries=extra_binaries,
    datas=[
        ('app/resources/fonts', 'app/resources/fonts'),
        (str(ffmpeg_dir), 'ffmpeg'),
    ] + extra_datas,
    hiddenimports=extra_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='viedub-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='viedub-backend',
)
