from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("candidate", [False, True])
def test_candidate_builder_preserves_prototype_and_uses_installer_names(tmp_path, monkeypatch, candidate):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    build = importlib.import_module("build_qt")
    calls = []
    monkeypatch.setattr(build.importlib.metadata, "version", lambda name: "1.2.3")
    monkeypatch.setattr(build.subprocess, "run", lambda command, **kwargs: calls.append((command, kwargs)))
    monkeypatch.setattr(build, "write_notices", lambda bundle, root: bundle / "notices")
    bundle = build.build(candidate=candidate, with_cli=True, dist=tmp_path / "dist", work=tmp_path / "work")
    assert bundle.name == ("CogStash-1.2.3-onedir" if candidate else "CogStash-Qt-Prototype")
    ui, cli = [command for command, kwargs in calls]
    assert any(value.endswith("candidate.py" if candidate else "qt/__main__.py") or value.endswith("qt\\__main__.py") for value in ui)
    assert "--onedir" in ui and "--copy-metadata" in ui
    assert "--onefile" in cli and "CogStash-CLI-1.2.3" in cli
    for module in ("PySide6", "pynput", "tkinter", "pystray", "PIL"):
        assert cli[cli.index(module) - 1] == "--exclude-module"
    assert all(kwargs["check"] for command, kwargs in calls)


def test_archive_inspection_checks_pyz_and_carchive_entries(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    smoke = importlib.import_module("smoke_qt")
    from types import SimpleNamespace
    archive = SimpleNamespace(toc={"PYZ.pyz": None, "native.dll": None}, open_embedded_archive=lambda name: SimpleNamespace(toc={"cogstash.core": None, "PySide6.QtCore": None}))
    monkeypatch.setattr(smoke, "CArchiveReader", lambda path: archive)
    names = smoke.archive_modules(Path("binary"))
    assert "native.dll" in names and "cogstash.core" in names
    with pytest.raises(AssertionError, match="PySide6.QtCore"):
        smoke.assert_excluded(names, ("PySide6",))
    smoke.assert_excluded({"argparse", "cogstash.core"}, ("PySide6", "cogstash.ui"))


def test_qt_builder_rejects_untested_python_range(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    build = importlib.import_module("build_qt")
    monkeypatch.setattr(sys, "version_info", (3, 15, 0))
    with pytest.raises(RuntimeError, match="3.10 through 3.14"):
        build.build(candidate=True, with_cli=False, dist=tmp_path, work=tmp_path)
