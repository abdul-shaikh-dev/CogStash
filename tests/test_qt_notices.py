from __future__ import annotations

import importlib.metadata as metadata
import importlib.util
import json
import runpy
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def collector(monkeypatch, tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts/qt_notices.py"
    spec = importlib.util.spec_from_file_location("qt_notices_test", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "project"
    root.mkdir()
    (root / "LICENSE").write_text("Project license", encoding="utf-8")
    qt = root / "third_party" / f"qt-{module.QT_VERSION}"
    qt.mkdir(parents=True)
    license_path = qt / "LGPL.txt"
    license_path.write_text("Test Qt license", encoding="utf-8")
    (qt / "sources.json").write_text(json.dumps([
        {"file": "LGPL.txt", "sha256": module.sha256(license_path)}
    ]), encoding="utf-8")
    python = tmp_path / "python"
    python.mkdir()
    (python / "LICENSE.txt").write_text("Python license", encoding="utf-8")
    monkeypatch.setattr(module.sys, "base_prefix", str(python))
    package = tmp_path / "package"
    package.mkdir()
    (package / "LICENSE").write_text("Dependency license", encoding="utf-8")
    distribution = SimpleNamespace(
        version=module.QT_VERSION, metadata={"License-Expression": "MIT"},
        files=[metadata.PackagePath("LICENSE")], locate_file=lambda p: package / p,
    )
    monkeypatch.setattr(module, "runtime_distributions", lambda: {"pyside6-essentials": distribution})
    monkeypatch.setattr(module.metadata, "distribution", lambda name: distribution)
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "app.exe").write_bytes(b"synthetic executable")
    return module, root, bundle, distribution


def test_collects_unchanged_licenses_and_hashes_payload(collector):
    module, root, bundle, _ = collector
    notices = module.write_notices(bundle, root)
    report = json.loads((notices / "inventory.json").read_text(encoding="utf-8"))
    assert (notices / "CogStash-LICENSE.txt").read_bytes() == (root / "LICENSE").read_bytes()
    assert report["review_status"] == "incomplete"
    assert report["bundled_files_excluding_notices"] == [
        {"path": "app.exe", "bytes": 20, "sha256": module.sha256(bundle / "app.exe")}
    ]
    for entry in report["notice_files"]:
        assert module.sha256(notices / entry["path"]) == entry["sha256"]
    assert report["components"][0]["notice_files"]
    with pytest.raises(FileExistsError):
        module.write_notices(bundle, root)


def test_rejects_changed_pinned_license_without_partial_output(collector):
    module, root, bundle, _ = collector
    (root / "third_party" / f"qt-{module.QT_VERSION}" / "LGPL.txt").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        module.write_notices(bundle, root)
    assert not (bundle / "notices").exists()
    assert not list(bundle.parent.glob("cogstash-notices-*"))


def test_missing_notice_is_reported_as_unresolved(collector):
    module, root, bundle, distribution = collector
    distribution.files = []
    notices = module.write_notices(bundle, root)
    report = json.loads((notices / "inventory.json").read_text(encoding="utf-8"))
    assert any("No installed notice files" in item for item in report["review_required"])


def test_rejects_notice_path_outside_distribution(collector):
    module, root, bundle, distribution = collector
    distribution.files = [metadata.PackagePath("../LICENSE")]
    with pytest.raises(ValueError, match="Unexpected notice path"):
        module.write_notices(bundle, root)
    assert not (bundle / "notices").exists()


def test_qt_version_change_requires_license_update(collector):
    module, root, bundle, distribution = collector
    distribution.version = "99.0.0"
    with pytest.raises(ValueError, match="pinned Qt"):
        module.write_notices(bundle, root)
    assert not (bundle / "notices").exists()


@pytest.mark.parametrize("build_succeeds", [True, False])
def test_notices_are_generated_only_after_successful_build(monkeypatch, build_succeeds):
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    import qt_notices

    events = []

    def build(*args, **kwargs):
        events.append("build")
        if not build_succeeds:
            raise subprocess.CalledProcessError(1, "PyInstaller")

    def collect(bundle, root):
        events.append("notices")
        assert bundle == root / "dist/qt-prototype/CogStash-Qt-Prototype"
        return bundle / "notices"

    monkeypatch.setattr(subprocess, "run", build)
    monkeypatch.setattr(qt_notices, "write_notices", collect)
    if build_succeeds:
        runpy.run_path(str(scripts / "build_qt.py"), run_name="__main__")
        assert events == ["build", "notices"]
    else:
        with pytest.raises(subprocess.CalledProcessError):
            runpy.run_path(str(scripts / "build_qt.py"), run_name="__main__")
        assert events == ["build"]
