#!/usr/bin/env python3
"""Copy the license files of every installed Python package into one folder.

build_offline_bundle_windows.bat runs this inside the build environment so the
packaged app ships the license text of every library it bundles, including the
many small dependencies that licenses\\README.txt does not list by name.

Usage: python collect_licenses.py <output folder>
"""
from __future__ import annotations

import re
import shutil
import sys
from importlib import metadata
from pathlib import Path

LICENSE_FILE_RE = re.compile(r"^(licen[cs]e|copying|notice|authors)", re.IGNORECASE)
METADATA_DIR_RE = re.compile(r"\.(dist|egg)-info$", re.IGNORECASE)


def license_files(dist: metadata.Distribution) -> list[Path]:
    """Return license-like files that live in the package's metadata folder."""
    found: list[Path] = []
    for rel in dist.files or []:
        if not LICENSE_FILE_RE.match(rel.name) or rel.suffix.lower() == ".py":
            continue
        # Only look inside *.dist-info / *.egg-info (including a licenses/
        # subfolder there), so modules that merely have "license" in their name
        # are not picked up.
        if not any(METADATA_DIR_RE.search(part) for part in rel.parts[:-1]):
            continue
        path = Path(dist.locate_file(rel))
        if path.is_file():
            found.append(path)
    return found


def collect_conda_licenses(out_dir: Path) -> int:
    """Copy info/licenses from each Conda package installed in this environment.

    Native libraries such as Qt, FFmpeg, MKL and the Intel OpenMP runtime come
    from Conda packages, not pip, so their license files are only found here.
    """
    import json

    conda_meta = Path(sys.prefix) / "conda-meta"
    if not conda_meta.is_dir():
        return 0

    packages = 0
    for record_path in sorted(conda_meta.glob("*.json")):
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        pkg_dir = record.get("extracted_package_dir")
        if not pkg_dir:
            continue
        licenses_dir = Path(pkg_dir) / "info" / "licenses"
        if not licenses_dir.is_dir():
            continue
        dest = out_dir / f"{record.get('name', record_path.stem)}-{record.get('version', '')}"
        shutil.copytree(licenses_dir, dest, dirs_exist_ok=True)
        packages += 1
    return packages


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    out_dir = Path(sys.argv[1]).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    conda_packages = collect_conda_licenses(out_dir / "conda")
    if conda_packages:
        print(f"Collected license files for {conda_packages} Conda packages")
    out_dir = out_dir / "pip"
    out_dir.mkdir(parents=True, exist_ok=True)

    packages = 0
    missing: list[str] = []
    for dist in sorted(metadata.distributions(), key=lambda d: (d.metadata["Name"] or "").lower()):
        name = dist.metadata["Name"] or "unknown"
        files = license_files(dist)
        if not files:
            license_field = dist.metadata["License-Expression"] or dist.metadata["License"] or "unknown"
            missing.append(f"{name} {dist.version}: {license_field.splitlines()[0][:80]}")
            continue

        dest = out_dir / f"{name}-{dist.version}"
        dest.mkdir(parents=True, exist_ok=True)
        for src in files:
            target = dest / src.name
            if target.exists():
                target = dest / f"{src.parent.name}-{src.name}"
            shutil.copyfile(src, target)
        packages += 1

    if missing:
        (out_dir / "_no_license_file.txt").write_text(
            "These packages ship no license file in their metadata. The license\n"
            "declared in their package metadata is listed instead:\n\n"
            + "\n".join(missing)
            + "\n",
            encoding="utf-8",
        )

    print(f"Collected license files for {packages} packages into {out_dir}")
    if missing:
        print(f"{len(missing)} packages had no license file; see _no_license_file.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
