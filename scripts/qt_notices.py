"""Collect available notices and an inventory for the diagnostic Qt bundle.

This is not a complete license review or an SPDX SBOM.
"""
from __future__ import annotations

import hashlib
import importlib.metadata as metadata
import json
import shutil
import sys
import sysconfig
import tempfile
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

QT_VERSION = "6.11.2"
REVIEW_REQUIRED = [
    "Match Qt third-party attributions and source availability to the actual wheel build.",
    "Review native DLL licenses, including OpenSSL, image codecs, and Microsoft runtimes.",
    "Verify all source, replacement/relinking, copyright, and distribution obligations before release.",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def runtime_distributions() -> dict[str, metadata.Distribution]:
    pending = ["PySide6-Essentials", "pynput", "Pillow"]
    found = {}
    while pending:
        name = canonicalize_name(pending.pop())
        if name in found:
            continue
        distribution = metadata.distribution(name)
        found[name] = distribution
        for value in distribution.requires or []:
            requirement = Requirement(value)
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
                pending.append(requirement.name)
    return found


def bundle_inventory(bundle: Path) -> list[dict[str, object]]:
    return [
        {"path": path.relative_to(bundle).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)}
        for path in sorted(bundle.rglob("*"))
        if path.is_file() and path.relative_to(bundle).parts[0] != "notices"
    ]


def refresh_staged_inventory(bundle: Path) -> None:
    """Record renamed executables and the CLI/shim added by installer staging."""
    path = bundle / "notices" / "inventory.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("format") != "cogstash-diagnostic-inventory-v1":
        raise ValueError("Unknown diagnostic inventory format")
    report["bundled_files_excluding_notices"] = bundle_inventory(bundle)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def write_notices(bundle: Path, root: Path) -> Path:
    if not bundle.is_dir() or not any(bundle.iterdir()):
        raise ValueError("Build the bundle before collecting notices")
    destination = bundle / "notices"
    if destination.exists():
        raise FileExistsError("Notices already exist; use a fresh build to avoid stale inventory")
    distributions = runtime_distributions()
    if distributions["pyside6-essentials"].version != QT_VERSION:
        raise ValueError("Update the pinned Qt license sources when changing the Qt version")
    # The frozen executable contains the PyInstaller bootloader, not its build dependency tree.
    distributions["pyinstaller"] = metadata.distribution("PyInstaller")
    bundled_files = bundle_inventory(bundle)
    with tempfile.TemporaryDirectory(prefix="cogstash-notices-", dir=bundle.parent) as temporary:
        staging = Path(temporary) / "notices"
        staging.mkdir()
        shutil.copyfile(root / "LICENSE", staging / "CogStash-LICENSE.txt")
        candidates = [Path(sys.base_prefix) / "LICENSE.txt", Path(sys.base_prefix) / "LICENSE",
                      Path(sysconfig.get_path("stdlib")) / "LICENSE.txt"]
        python_license = next((path for path in candidates if path.is_file()), None)
        if python_license is None:
            raise FileNotFoundError("Python runtime LICENSE.txt is required for this diagnostic build")
        shutil.copyfile(python_license, staging / "Python-LICENSE.txt")
        qt_sources = root / "third_party" / f"qt-{QT_VERSION}"
        sources = json.loads((qt_sources / "sources.json").read_text(encoding="utf-8"))
        for source in sources:
            if sha256(qt_sources / source["file"]) != source["sha256"]:
                raise ValueError(f"Qt license checksum mismatch: {source['file']}")
        shutil.copytree(qt_sources, staging / f"qt-{QT_VERSION}")
        components = []
        missing = []
        for name, distribution in sorted(distributions.items()):
            copied = []
            for file in distribution.files or []:
                if not any(part.lower().startswith(("license", "copying", "notice")) for part in file.parts):
                    continue
                if file.is_absolute() or ".." in file.parts:
                    raise ValueError(f"Unexpected notice path in {name}: {file}")
                source_path = Path(distribution.locate_file(file))
                if not source_path.is_file():
                    raise FileNotFoundError(source_path)
                target = staging / name / file
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source_path, target)
                copied.append(target.relative_to(staging).as_posix())
            if not copied:
                missing.append(f"No installed notice files found for {name}")
            components.append({
                "name": name, "version": distribution.version,
                "role": "bootloader/build tool" if name == "pyinstaller" else "runtime dependency",
                "declared_license": distribution.metadata.get("License-Expression") or distribution.metadata.get("License"),
                "notice_files": copied,
            })
        report = {
            "format": "cogstash-diagnostic-inventory-v1", "python": sys.version.split()[0],
            "review_status": "incomplete", "review_required": REVIEW_REQUIRED + missing,
            "components": components,
            "bundled_files_excluding_notices": bundled_files,
            "notice_files": [
                {"path": p.relative_to(staging).as_posix(), "sha256": sha256(p)}
                for p in sorted(staging.rglob("*")) if p.is_file()
            ],
        }
        (staging / "inventory.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        (staging / "README.txt").write_text(
            "CogStash diagnostic bundle notices\n\n"
            "License files are copied unchanged from the project, Python installation, installed distributions, "
            "and pinned Qt source files. Inventory hashes describe this bundle before this notices directory was added.\n\n"
            "Review status: INCOMPLETE. This inventory is not a full SBOM or release clearance.\n"
            "Qt wheel metadata declares open-source options, but the wheel includes only a commercial-license "
            "reference. The matching Qt LGPLv3 and GPLv3 texts are included separately; that commercial reference "
            "does not indicate that CogStash has a commercial Qt license.\n\n"
            + "\n".join("- " + item for item in REVIEW_REQUIRED + missing) + "\n\n"
            "https://doc.qt.io/qt-6.11/licenses-used-in-qt.html\n"
            "https://doc.qt.io/qt-6.11/sbom.html\n"
            "https://www.qt.io/development/open-source-lgpl-obligations\n",
            encoding="utf-8",
        )
        staging.rename(destination)
    return destination
