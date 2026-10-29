# -*- mode: python ; coding: utf-8 -*-
from __future__ import annotations

import fnmatch
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

_spec_file = globals().get("__file__") or globals().get("SPEC")
ROOT = Path(_spec_file).resolve().parent if _spec_file else Path.cwd().resolve()


def should_keep_binary(entry: tuple[str, ...]) -> bool:
    if not entry:
        return False
    src = entry[0]
    name = os.path.basename(src).lower()
    if fnmatch.fnmatch(name, "vcomp*.dll"):
        return False
    if fnmatch.fnmatch(name, "libiomp*.dll"):
        return False
    if name == "libomp.dll":
        return False
    return True


def dedupe_openmp_runtime(binaries: list[tuple]) -> list[tuple]:
    """Keep a single libiomp5md.dll at the bundle root.

    PyInstaller's torch/MKL hook ships one libiomp5md.dll at the bundle root,
    while its automatic binary-dependency analysis also collects ctranslate2's
    own copy under ctranslate2\\. Both then load into the process and abort the
    app the moment a model loads with:
        OMP: Error #15: Initializing libiomp5md.dll, but found
                        libiomp5md.dll already initialized.
    should_keep_binary() runs before Analysis and only sees the manually
    collected binaries, so it cannot remove these hook/auto-added copies.
    Dedupe here, after Analysis, preferring the root copy so that both torch
    and ctranslate2 resolve to the same single OpenMP runtime.
    """
    iomp = [b for b in binaries if os.path.basename(b[0]).lower() == "libiomp5md.dll"]
    if len(iomp) <= 1:
        return binaries
    # Prefer a copy already destined for the bundle root (the torch/MKL one,
    # which we verified both consumers can share).
    iomp.sort(key=lambda b: (os.path.dirname(b[0]) != "", b[0]))
    chosen = ("libiomp5md.dll", iomp[0][1], iomp[0][2])
    rest = [b for b in binaries if os.path.basename(b[0]).lower() != "libiomp5md.dll"]
    return rest + [chosen]


datas = []
binaries = []
hiddenimports = [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "shiboken6",
    "shiboken6.Shiboken",
    "pyannote.audio",
    "pyannote.core",
    "pyannote.pipeline",
]
hiddenimports += collect_submodules("pyannote.audio")
hiddenimports += collect_submodules("pyannote.audio.pipelines")
hiddenimports += collect_submodules("speechbrain")

for package in [
    "faster_whisper",
    "ctranslate2",
    "tokenizers",
    "PySide6",
    "shiboken6",
    "numpy",
    "av",
    "lightning_fabric",
    "lightning_utilities",
    "pytorch_lightning",
    "speechbrain",
]:
    datas += collect_data_files(package)
    binaries += collect_dynamic_libs(package)

# speechbrain inspects package files from disk at runtime, so include .py files too.
datas += collect_data_files("speechbrain", include_py_files=True)

for package in ["torch", "torchaudio", "pyannote.audio", "pyannote.core", "pyannote.pipeline"]:
    datas += collect_data_files(package)
    binaries += collect_dynamic_libs(package)

for model_name in [
    "faster-whisper-medium",
    "faster-whisper-large-v3",
    "pyannote-speaker-diarization-3.1",
    "pyannote-segmentation-3.0",
    "pyannote-wespeaker-voxceleb-resnet34-LM",
    "speechbrain-spkrec-ecapa-voxceleb",
]:
    datas.append((str(ROOT / "models" / model_name), f"models/{model_name}"))

_icon_png = ROOT / "assets" / "app_icon.png"
_icon_ico = ROOT / "assets" / "app_icon.ico"
if _icon_png.exists():
    datas.append((str(_icon_png), "assets"))

binaries = [entry for entry in binaries if should_keep_binary(entry)]

a = Analysis(
    [str(ROOT / "offline_transcribe_gui.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
a.binaries = dedupe_openmp_runtime(a.binaries)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WhisperOffline",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(_icon_ico) if _icon_ico.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="WhisperOffline",
)
