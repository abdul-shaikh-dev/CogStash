#!/usr/bin/env python3
"""Build the Windows CogStash installer from a staged PyInstaller bundle."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from importlib.metadata import version as package_version
from pathlib import Path

try:
    from scripts import _artifacts
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import _artifacts  # type: ignore[no-redef]

get_staged_app_dirname = _artifacts.get_staged_app_dirname
get_staged_cli_bin_dirname = _artifacts.get_staged_cli_bin_dirname
get_staged_cli_exe_name = _artifacts.get_staged_cli_exe_name
get_staged_cli_shim_name = _artifacts.get_staged_cli_shim_name
get_staged_ui_exe_name = _artifacts.get_staged_ui_exe_name
windows_artifact_layout = _artifacts.windows_artifact_layout
get_staged_app_dirname.__module__ = "_artifacts"
get_staged_cli_bin_dirname.__module__ = "_artifacts"
get_staged_cli_exe_name.__module__ = "_artifacts"
get_staged_cli_shim_name.__module__ = "_artifacts"
get_staged_ui_exe_name.__module__ = "_artifacts"
windows_artifact_layout.__module__ = "_artifacts"

ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = ROOT / "build"
DIST_DIR = ROOT / "dist"
ISS_PATH = ROOT / "installer" / "windows" / "CogStash.iss"


def get_version() -> str:
    """Get the installed package version."""
    return package_version("cogstash")


def make_version_info_version(version: str) -> str:
    """Convert a package version string into a numeric Windows file version."""
    parts = re.findall(r"\d+", version)
    numeric_parts = parts[:4]
    while len(numeric_parts) < 4:
        numeric_parts.append("0")
    return ".".join(numeric_parts)


def find_windows_onedir_bundle(dist_dir: Path, version: str) -> Path:
    """Locate the Windows onedir bundle created by scripts/build.py."""
    layout = windows_artifact_layout(version=version, dist_dir=dist_dir)
    bundle_dir = layout.onedir_dir
    if not bundle_dir.is_dir():
        raise FileNotFoundError(f"Windows onedir bundle not found: {bundle_dir}")

    bundle_exe = layout.onedir_exe
    if not bundle_exe.is_file():
        raise FileNotFoundError(f"Expected bundle executable not found: {bundle_exe}")

    return bundle_dir


def find_windows_cli_binary(dist_dir: Path, version: str) -> Path:
    """Locate the Windows CLI onefile binary created by scripts/build.py."""
    cli_binary = windows_artifact_layout(version=version, dist_dir=dist_dir).cli_exe
    if not cli_binary.is_file():
        raise FileNotFoundError(f"Windows CLI binary not found: {cli_binary}")
    return cli_binary


def _cli_shim_contents() -> str:
    """Return the batch shim used for PATH-based CLI invocation on Windows."""
    return '@echo off\n"%~dp0..\\' + get_staged_cli_exe_name() + '" %*\n'


def stage_windows_payload(*, bundle_dir: Path, cli_binary: Path, version: str, staging_root: Path) -> Path:
    """Copy the versioned onedir bundle into a versionless installer payload."""
    layout = windows_artifact_layout(version=version, dist_dir=bundle_dir.parent)
    staged_dir = staging_root / get_staged_app_dirname()
    if staged_dir.exists():
        shutil.rmtree(staged_dir)

    staging_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(bundle_dir, staged_dir)

    versioned_exe = staged_dir / layout.onedir_exe.name
    staged_exe = staged_dir / get_staged_ui_exe_name()
    versioned_exe.rename(staged_exe)
    shutil.copy2(cli_binary, staged_dir / get_staged_cli_exe_name())
    cli_bin_dir = staged_dir / get_staged_cli_bin_dirname()
    cli_bin_dir.mkdir()
    (cli_bin_dir / get_staged_cli_shim_name()).write_text(_cli_shim_contents(), encoding="utf-8")
    if (staged_dir / "notices" / "inventory.json").is_file():
        try:
            from scripts.qt_notices import refresh_staged_inventory
        except ModuleNotFoundError:
            from qt_notices import refresh_staged_inventory
        refresh_staged_inventory(staged_dir)
    return staged_dir


def compile_installer(*, compiler: str, iss_path: Path, version: str, source_dir: Path, output_dir: Path) -> None:
    """Invoke Inno Setup with the staged payload and output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    version_info_version = make_version_info_version(version)

    cmd = [
        compiler,
        f"/DAppVersion={version}",
        f"/DVersionInfoVersion={version_info_version}",
        f"/DSourceDir={source_dir.resolve()}",
        f"/DOutputDir={output_dir.resolve()}",
        str(iss_path.resolve()),
    ]
    subprocess.run(cmd, check=True)


def build_installer(
    *,
    version: str,
    dist_dir: Path = DIST_DIR,
    build_dir: Path = BUILD_DIR,
    iss_path: Path = ISS_PATH,
    compiler: str = "iscc",
    output_dir: Path = DIST_DIR,
) -> Path:
    """Stage the onedir payload and compile the Windows installer."""
    if not iss_path.is_file():
        raise FileNotFoundError(f"Inno Setup script not found: {iss_path}")

    bundle_dir = find_windows_onedir_bundle(dist_dir=dist_dir, version=version)
    cli_binary = find_windows_cli_binary(dist_dir=dist_dir, version=version)
    staged_dir = stage_windows_payload(
        bundle_dir=bundle_dir,
        cli_binary=cli_binary,
        version=version,
        staging_root=build_dir / "installer",
    )
    compile_installer(
        compiler=compiler,
        iss_path=iss_path,
        version=version,
        source_dir=staged_dir,
        output_dir=output_dir,
    )
    return staged_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the CogStash Windows installer")
    parser.add_argument("--version", default=get_version(), help="Package version to package into the installer")
    parser.add_argument("--dist-dir", type=Path, default=DIST_DIR, help="Directory containing PyInstaller outputs")
    parser.add_argument("--build-dir", type=Path, default=BUILD_DIR, help="Directory used for staged installer files")
    parser.add_argument("--iss-path", type=Path, default=ISS_PATH, help="Path to the Inno Setup .iss file")
    parser.add_argument("--compiler", default="iscc", help="Inno Setup compiler executable")
    parser.add_argument("--output-dir", type=Path, default=DIST_DIR, help="Directory for the final setup executable")
    args = parser.parse_args()

    staged_dir = build_installer(
        version=args.version,
        dist_dir=args.dist_dir,
        build_dir=args.build_dir,
        iss_path=args.iss_path,
        compiler=args.compiler,
        output_dir=args.output_dir,
    )
    print(f"Staged installer payload: {staged_dir}")
    print(f"Installer output directory: {args.output_dir}")


if __name__ == "__main__":
    main()
