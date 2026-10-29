#!/usr/bin/env python3
"""One-time setup the packaged Windows app does for itself on first launch.

This is what lets users simply double-click WhisperOffline.exe, with no
launcher script:
  * removes the "downloaded from the internet" mark (the Zone.Identifier
    stream) from the app's files, so Windows stops showing a security prompt
    on every launch
  * hides the _internal folder, so the app folder only shows what users need
  * adds "Whisper Offline" shortcuts to the desktop and the Start menu

Setup runs again only if the app folder is moved, so a shortcut the user
deleted is not re-created on every launch.
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import threading
from pathlib import Path

APP_NAME = "Whisper Offline"
MARKER_NAME = ".setup_done"

FILE_ATTRIBUTE_HIDDEN = 0x2
INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF
CSIDL_PROGRAMS = 0x0002  # Start menu > Programs
CSIDL_DESKTOPDIRECTORY = 0x0010
CREATE_NO_WINDOW = 0x08000000


def unblock_files(root: Path) -> None:
    """Delete the Zone.Identifier stream Windows attaches to downloaded files."""
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            os.remove(f"{path}:Zone.Identifier")
        except OSError:
            pass


def hide_folder(path: Path) -> None:
    kernel32 = ctypes.windll.kernel32
    kernel32.GetFileAttributesW.restype = ctypes.c_uint32
    attrs = kernel32.GetFileAttributesW(str(path))
    if attrs != INVALID_FILE_ATTRIBUTES and not attrs & FILE_ATTRIBUTE_HIDDEN:
        kernel32.SetFileAttributesW(str(path), attrs | FILE_ATTRIBUTE_HIDDEN)


def shell_folder(csidl: int) -> Path | None:
    """Return a per-user shell folder (follows OneDrive desktop redirection)."""
    buf = ctypes.create_unicode_buffer(260)
    if ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf) != 0 or not buf.value:
        return None
    return Path(buf.value)


def _ps_quote(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def create_shortcut(link: Path, target: Path) -> None:
    script = (
        f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({_ps_quote(link)}); "
        f"$s.TargetPath = {_ps_quote(target)}; "
        f"$s.WorkingDirectory = {_ps_quote(target.parent)}; "
        f"$s.IconLocation = {_ps_quote(f'{target},0')}; "
        "$s.Save()"
    )
    powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    subprocess.run(
        [str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=True,
        timeout=60,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW,
    )


def run_setup(exe: Path, shortcut_dirs: list[Path] | None = None) -> bool:
    """Do first-run setup for the app at exe.parent. Returns True if it ran."""
    app_dir = exe.parent
    internal = app_dir / "_internal"
    marker = internal / MARKER_NAME
    try:
        if marker.read_text(encoding="utf-8").strip() == str(exe):
            return False
    except OSError:
        pass

    unblock_files(app_dir)
    if internal.is_dir():
        hide_folder(internal)

    if shortcut_dirs is None:
        shortcut_dirs = [d for d in (shell_folder(CSIDL_DESKTOPDIRECTORY), shell_folder(CSIDL_PROGRAMS)) if d]
    for folder in shortcut_dirs:
        try:
            create_shortcut(folder / f"{APP_NAME}.lnk", exe)
        except (OSError, subprocess.SubprocessError):
            pass

    try:
        marker.write_text(str(exe), encoding="utf-8")
    except OSError:
        pass
    return True


def start_first_run_setup() -> None:
    """Run first-launch setup in the background (packaged Windows app only)."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return
    exe = Path(sys.executable).resolve()
    threading.Thread(target=run_setup, args=(exe,), daemon=True).start()
