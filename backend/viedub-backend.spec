# -*- mode: python ; coding: utf-8 -*-
# Slim backend: the heavy parts (torch/demucs/speechbrain/faster-whisper/... and ffmpeg)
# are NOT bundled. They are downloaded on first use as "packs" (app/core/packs.py);
# the AI pack is built by scripts/build-ai-pack.mjs.

# Everything that ships in the AI pack must be excluded here, otherwise PyInstaller
# would still bundle it (it is installed in the build venv) and the installer stays big.
AI_PACK_MODULES = [
    'torch', 'torchaudio', 'torchvision', 'demucs', 'speechbrain', 'faster_whisper',
    'ctranslate2', 'av', 'onnxruntime', 'sklearn', 'scipy', 'numpy', 'hyperpyyaml',
    'sentencepiece', 'tokenizers', 'huggingface_hub', 'hf_xet', 'julius', 'lameenc',
    'openunmix', 'dora', 'treetable', 'einops', 'diffq', 'numba', 'llvmlite', 'sphn',
]

# Stdlib modules that the downloadable AI pack (torch, demucs, speechbrain, scipy,
# sklearn, ...) imports but the slim backend itself never touches, so PyInstaller would
# otherwise leave them out. Cheap: they are small and compress well.
STDLIB_FOR_AI_PACK = [
    'timeit', 'unittest', 'unittest.mock', 'doctest', 'pdb', 'bdb', 'cmd', 'code', 'codeop',
    'cProfile', 'profile', 'pstats', 'trace', 'tracemalloc', 'sched', 'tokenize', 'difflib',
    'pydoc', 'runpy', 'inspect', 'dis', 'opcode', 'ast', 'textwrap', 'fractions',
    'statistics', 'decimal', 'secrets', 'graphlib', 'zoneinfo', 'tomllib', 'csv',
    'configparser', 'optparse', 'getpass', 'locale', 'platform', 'gzip', 'bz2', 'lzma',
    'zipfile', 'zipimport', 'tarfile', 'sqlite3', 'ctypes', 'ctypes.util', 'uuid', 'shlex',
    'wave', 'colorsys', 'sndhdr', 'imghdr', 'pickletools', 'copyreg', 'numbers',
    'multiprocessing.pool', 'multiprocessing.shared_memory', 'multiprocessing.managers',
    'concurrent.futures', 'xml.etree.ElementTree', 'xml.dom.minidom', 'html.parser',
    'http.client', 'http.server', 'email.mime.text', 'urllib.request', 'urllib.parse',
    'logging.handlers', 'queue', 'heapq', 'bisect', 'array', 'mmap', 'select', 'selectors',
    'socketserver', 'ssl', 'hashlib', 'hmac', 'binascii', 'base64', 'struct', 'pprint',
    'contextvars', 'weakref', 'gc', 'abc', 'typing', 'enum', 'functools', 'itertools',
    'operator', 'collections.abc', 'importlib.metadata', 'importlib.resources',
    'importlib.util', 'pkgutil', 'site', 'sysconfig', 'tempfile', 'shutil', 'glob',
    'fnmatch', 'stat', 'filecmp', 'signal', 'faulthandler', 'readline', 'curses',
    'turtle', 'webbrowser', 'smtplib', 'ftplib', 'telnetlib', 'xmlrpc.client', 'json.tool',
]

a = Analysis(
    ['app/entrypoint.py'],
    pathex=[],
    binaries=[],
    datas=[('app/resources/fonts', 'app/resources/fonts')],
    hiddenimports=STDLIB_FOR_AI_PACK,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # GUI/notebook/test libraries are never used by the backend.
    excludes=AI_PACK_MODULES
    + ['tkinter', 'matplotlib', 'IPython', 'jupyter', 'notebook', 'pytest', 'sphinx'],
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
    upx=False,
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
    upx=False,
    upx_exclude=[],
    name='viedub-backend',
)
