"""Tests for Windows installer build helpers."""

from __future__ import annotations

import importlib.util
import re
import runpy
import sys
import uuid
from pathlib import Path

import pytest


def _scripts_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "scripts"


def _ensure_scripts_dir_on_path() -> None:
    scripts_dir = str(_scripts_dir())
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)


def _load_artifacts_module():
    _ensure_scripts_dir_on_path()
    module_path = _scripts_dir() / "_artifacts.py"
    spec = importlib.util.spec_from_file_location("_artifacts", module_path)
    assert spec is not None
    assert spec.loader is not None
    if spec.name in sys.modules:
        return sys.modules[spec.name]
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_build_installer_module():
    _ensure_scripts_dir_on_path()
    module_path = _scripts_dir() / "build_installer.py"
    spec = importlib.util.spec_from_file_location("build_installer", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_build_module():
    _ensure_scripts_dir_on_path()
    module_path = _scripts_dir() / "build.py"
    spec = importlib.util.spec_from_file_location("build_script", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_artifact_contract_module():
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "scripts" / "_artifacts.py"
    assert module_path.is_file(), f"Shared artifact contract not found: {module_path}"
    spec = importlib.util.spec_from_file_location("_artifacts", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_script_source(relative_path: str) -> str:
    repo_root = Path(__file__).resolve().parents[1]
    return (repo_root / relative_path).read_text(encoding="utf-8")


def test_inno_setup_script_uses_per_user_defaults():
    """Installer script should target a per-user install with standard shortcuts."""
    repo_root = Path(__file__).resolve().parents[1]
    iss_path = repo_root / "installer" / "windows" / "CogStash.iss"

    content = iss_path.read_text(encoding="utf-8")

    assert 'DefaultDirName={localappdata}\\Programs\\CogStash' in content
    assert "PrivilegesRequired=lowest" in content
    assert "OutputBaseFilename=CogStash-v{#AppVersion}-setup" in content
    assert 'Name: "{group}\\CogStash"; Filename: "{app}\\CogStash.exe"' in content


def test_artifact_contract_build_names():
    module = _load_artifacts_module()

    assert module.get_executable_name(target="ui", bundle_mode="onefile", version="1.2.3") == "CogStash-1.2.3"
    assert module.get_executable_name(target="ui", bundle_mode="onedir", version="1.2.3") == "CogStash-1.2.3-onedir"
    assert module.get_executable_name(target="cli", bundle_mode="onefile", version="1.2.3") == "CogStash-CLI-1.2.3"


def test_artifact_contract_windows_paths():
    module = _load_artifacts_module()

    dist_dir = Path("C:/tmp/dist")
    layout = module.windows_artifact_layout(version="1.2.3", dist_dir=dist_dir)

    assert layout.onedir_dir == dist_dir / "CogStash-1.2.3-onedir"
    assert layout.onedir_exe == layout.onedir_dir / "CogStash-1.2.3-onedir.exe"
    assert layout.cli_exe == dist_dir / "CogStash-CLI-1.2.3.exe"
    assert layout.staged_app_dirname == "CogStash"
    assert layout.staged_ui_exe_name == "CogStash.exe"
    assert layout.staged_cli_exe_name == "CogStash-CLI.exe"
    assert layout.staged_cli_bin_dirname == "bin"
    assert layout.staged_cli_shim_name == "cogstash.cmd"


def test_artifact_contract_release_archive_names():
    module = _load_artifacts_module()

    assert module.get_release_archive_name(tag="v1.2.3", platform_suffix="windows") == "CogStash-v1.2.3-windows.zip"
    assert module.get_release_archive_name(tag="v1.2.3", platform_suffix="macos") == "CogStash-v1.2.3-macos.zip"
    assert module.get_release_archive_name(tag="v1.2.3", platform_suffix="linux") == "CogStash-v1.2.3-linux.tar.gz"


def test_artifact_contract_staged_names():
    module = _load_artifacts_module()

    assert module.get_staged_app_dirname() == "CogStash"
    assert module.get_staged_ui_exe_name() == "CogStash.exe"
    assert module.get_staged_cli_exe_name() == "CogStash-CLI.exe"
    assert module.get_staged_cli_bin_dirname() == "bin"
    assert module.get_staged_cli_shim_name() == "cogstash.cmd"


def test_build_script_consumes_shared_artifact_contract():
    module = _load_build_module()

    assert module.get_executable_name.__module__ == "_artifacts"
    assert module.get_executable_name(target="ui", bundle_mode="onefile", version="1.2.3") == "CogStash-1.2.3"
    assert module.get_executable_name(target="cli", bundle_mode="onefile", version="1.2.3") == "CogStash-CLI-1.2.3"


def test_build_installer_consumes_shared_artifact_contract():
    module = _load_build_installer_module()

    assert module.windows_artifact_layout.__module__ == "_artifacts"
    assert module.get_staged_app_dirname.__module__ == "_artifacts"
    assert module.get_staged_ui_exe_name.__module__ == "_artifacts"
    assert module.get_staged_cli_exe_name.__module__ == "_artifacts"
    assert module.get_staged_cli_bin_dirname.__module__ == "_artifacts"
    assert module.get_staged_cli_shim_name.__module__ == "_artifacts"


def test_inno_setup_script_supports_optional_startup_task():
    """Installer should expose startup creation and remove that entry on uninstall."""
    repo_root = Path(__file__).resolve().parents[1]
    iss_path = repo_root / "installer" / "windows" / "CogStash.iss"

    content = iss_path.read_text(encoding="utf-8")

    assert 'Name: "startup"; Description: "Launch CogStash when I sign in"' in content
    assert "WizardIsTaskSelected('startup')" in content
    assert 'SaveStringToFile(ExpandConstant(\'{userstartup}\\CogStash.bat\')' in content
    assert 'ExpandConstant(\'{app}\\CogStash.exe\')' in content
    assert 'Type: files; Name: "{userstartup}\\CogStash.bat"' in content


def test_inno_setup_script_offers_optional_path_task_with_correct_description():
    """Installer script should offer an optional PATH task with the correct CLI description."""
    repo_root = Path(__file__).resolve().parents[1]
    iss_path = repo_root / "installer" / "windows" / "CogStash.iss"

    content = iss_path.read_text(encoding="utf-8")

    assert 'Name: "addtopath"; Description: "Add CogStash CLI to PATH"' in content
    assert "ChangesEnvironment=yes" in content
    assert "ExpandConstant('{app}\\bin')" in content


def test_shared_artifact_contract_defines_versioned_artifact_names():
    """Shared contract should own the versioned UI/CLI artifact naming rules."""
    contract = _load_artifact_contract_module()

    assert contract.get_executable_name(target="ui", bundle_mode="onefile", version="1.2.3") == "CogStash-1.2.3"
    assert contract.get_executable_name(target="ui", bundle_mode="onedir", version="1.2.3") == "CogStash-1.2.3-onedir"
    assert contract.get_executable_name(target="cli", bundle_mode="onefile", version="1.2.3") == "CogStash-CLI-1.2.3"


def test_shared_artifact_contract_defines_windows_layout_names():
    """Shared contract should centralize the Windows bundle and staged payload layout."""
    contract = _load_artifact_contract_module()

    assert contract.get_onedir_dir_name("1.2.3") == "CogStash-1.2.3-onedir"
    assert contract.get_onedir_exe_name("1.2.3") == "CogStash-1.2.3-onedir.exe"
    assert contract.get_windows_installer_app_dirname() == "CogStash"
    assert contract.get_windows_installer_exe_name() == "CogStash.exe"
    assert contract.get_windows_installer_cli_exe_name() == "CogStash-CLI.exe"
    assert contract.get_windows_installer_cli_bin_dirname() == "bin"
    assert contract.get_windows_installer_cli_shim_name() == "cogstash.cmd"


def test_shared_artifact_contract_defines_release_archive_names():
    """Shared contract should own the platform-specific release archive filenames."""
    contract = _load_artifact_contract_module()

    assert contract.get_release_archive_name(ref_name="v1.2.3", platform_suffix="windows") == "CogStash-v1.2.3-windows.zip"
    assert contract.get_release_archive_name(ref_name="v1.2.3", platform_suffix="macos") == "CogStash-v1.2.3-macos.zip"
    assert contract.get_release_archive_name(ref_name="v1.2.3", platform_suffix="linux") == "CogStash-v1.2.3-linux.tar.gz"


def test_build_scripts_import_shared_artifact_contract():
    """Build scripts should import the shared artifact contract instead of duplicating names."""
    build_source = _read_script_source("scripts/build.py")
    build_installer_source = _read_script_source("scripts/build_installer.py")
    import_pattern = re.compile(
        r"^\s*(?:from\s+scripts\s+import\s+_artifacts|import\s+scripts\._artifacts\s+as\s+_artifacts)\s*$",
        re.M,
    )

    assert import_pattern.search(build_source)
    assert import_pattern.search(build_installer_source)


def test_inno_setup_script_manages_installer_owned_path():
    """Installer script should add PATH and track ownership for safe removal on uninstall."""
    repo_root = Path(__file__).resolve().parents[1]
    iss_path = repo_root / "installer" / "windows" / "CogStash.iss"

    content = iss_path.read_text(encoding="utf-8")

    # Ownership registry key and write/delete operations must be present.
    assert "PathOwnershipKey" in content
    assert "RegWriteExpandStringValue" in content
    assert "RegDeleteValue" in content

    # Must use a segment-safe helper rather than raw StringReplace.
    assert "RemoveExactPathSegment" in content
    assert "StringReplace" not in content

    # Helper must split on semicolons — the delimiter for PATH segments.
    assert "Pos(';', " in content or "SemiPos" in content

    # Uninstall hook must call the removal procedure at the right step.
    assert "CurUninstallStepChanged" in content
    assert "usPostUninstall" in content
    assert "RemoveInstallerOwnedPath()" in content


def test_inno_setup_script_offers_optional_path_task():
    """Installer script should offer an optional PATH integration task (regression lock)."""
    repo_root = Path(__file__).resolve().parents[1]
    iss_path = repo_root / "installer" / "windows" / "CogStash.iss"
    content = iss_path.read_text(encoding="utf-8")
    assert 'Name: "addtopath"' in content
    assert "ChangesEnvironment=yes" in content


def test_inno_setup_script_coordinates_with_running_app_on_uninstall():
    """Installer script should coordinate with running app on uninstall (regression lock)."""
    repo_root = Path(__file__).resolve().parents[1]
    iss_path = repo_root / "installer" / "windows" / "CogStash.iss"
    content = iss_path.read_text(encoding="utf-8")
    assert "CloseApplications=yes" in content


def test_installed_startup_state_contract_is_implemented_in_config_and_ui():
    """Installed startup/config sync should be backed by config + UI code, not an installer comment marker."""
    repo_root = Path(__file__).resolve().parents[1]
    config_path = repo_root / "src" / "cogstash" / "core" / "config.py"
    settings_path = repo_root / "src" / "cogstash" / "ui" / "settings.py"
    install_state_path = repo_root / "src" / "cogstash" / "ui" / "install_state.py"
    iss_path = repo_root / "installer" / "windows" / "CogStash.iss"

    config_content = config_path.read_text(encoding="utf-8")
    settings_content = settings_path.read_text(encoding="utf-8")
    install_state_content = install_state_path.read_text(encoding="utf-8")
    iss_content = iss_path.read_text(encoding="utf-8")

    assert "last_seen_installer_version" in config_content
    assert "startup_script_exists" in settings_content
    assert "self.config.launch_at_startup = startup_state" in settings_content
    assert "INSTALL_MARKER_NAME" in install_state_content
    assert ".cogstash-installed" in iss_content


def test_stage_windows_payload_copies_bundle_and_renames_exe():
    """Stage helper should normalize app names and expose the CLI through a PATH-facing shim."""
    module = _load_build_installer_module()
    version = "1.2.3"
    repo_root = Path(__file__).resolve().parents[1]
    scratch_root = repo_root / ".tmp" / f"test-stage-windows-payload-{uuid.uuid4().hex}"
    bundle_dir = scratch_root / "dist" / f"CogStash-{version}-onedir"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / f"CogStash-{version}-onedir.exe").write_text("exe", encoding="utf-8")
    (bundle_dir / "support.dll").write_text("dll", encoding="utf-8")
    (bundle_dir / "assets").mkdir()
    (bundle_dir / "assets" / "icon.png").write_text("png", encoding="utf-8")
    cli_binary = scratch_root / "dist" / f"CogStash-CLI-{version}.exe"
    cli_binary.write_text("cli", encoding="utf-8")

    staged_dir = module.stage_windows_payload(
        bundle_dir=bundle_dir,
        cli_binary=cli_binary,
        version=version,
        staging_root=scratch_root / "build" / "installer",
    )

    assert staged_dir.name == "CogStash"
    assert (staged_dir / "CogStash.exe").read_text(encoding="utf-8") == "exe"
    assert (staged_dir / "CogStash-CLI.exe").read_text(encoding="utf-8") == "cli"
    cli_shim = staged_dir / "bin" / "cogstash.cmd"
    assert cli_shim.is_file()
    shim_contents = cli_shim.read_text(encoding="utf-8")
    assert "@echo off" in shim_contents
    assert '"%~dp0..\\CogStash-CLI.exe" %*' in shim_contents
    assert not (staged_dir / f"CogStash-{version}-onedir.exe").exists()
    assert (staged_dir / "support.dll").read_text(encoding="utf-8") == "dll"
    assert (staged_dir / "assets" / "icon.png").read_text(encoding="utf-8") == "png"


def test_compile_installer_invokes_iscc_with_expected_defines(monkeypatch):
    """ISCC should receive version, source, and output defines."""
    module = _load_build_installer_module()
    calls = []

    def fake_run(cmd, check):
        calls.append((cmd, check))

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    repo_root = Path(__file__).resolve().parents[1]
    scratch_root = repo_root / ".tmp" / f"test-compile-installer-{uuid.uuid4().hex}"
    scratch_root.mkdir(parents=True)
    iss_path = scratch_root / "CogStash.iss"
    iss_path.write_text("; mock", encoding="utf-8")
    source_dir = scratch_root / "payload"
    output_dir = scratch_root / "dist"

    module.compile_installer(
        compiler="iscc.exe",
        iss_path=iss_path,
        version="2.0.0",
        source_dir=source_dir,
        output_dir=output_dir,
    )

    assert calls == [
        (
            [
                "iscc.exe",
                "/DAppVersion=2.0.0",
                "/DVersionInfoVersion=2.0.0.0",
                f"/DSourceDir={source_dir}",
                f"/DOutputDir={output_dir}",
                str(iss_path),
            ],
            True,
        )
    ]


def test_build_script_uses_noconsole_on_windows_when_not_debug(monkeypatch):
    """Windows release builds should use the GUI subsystem to avoid a persistent console window."""
    module = _load_build_module()
    calls = []

    def fake_run(cmd, check):
        calls.append((cmd, check))

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module.sys, "platform", "win32")

    module.run_pyinstaller(target="ui", bundle_mode="onefile", debug=False, icon_path=None, version="1.2.3")

    assert calls, "Expected PyInstaller to be invoked"
    cmd, check = calls[0]
    assert "--noconsole" in cmd
    assert check is True


def test_build_script_cli_target_uses_cli_entrypoint_without_gui_hidden_imports(monkeypatch):
    """CLI target should build from the CLI bootstrap without tray hidden imports."""
    module = _load_build_module()
    calls = []

    def fake_run(cmd, check):
        calls.append((cmd, check))

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module.sys, "platform", "win32")

    module.run_pyinstaller(target="cli", bundle_mode="onefile", debug=False, icon_path=None, version="1.2.3")

    assert calls, "Expected PyInstaller to be invoked"
    cmd, check = calls[0]
    assert str(module.CLI_ENTRY) in cmd
    assert "--name" in cmd
    assert "CogStash-CLI-1.2.3" in cmd
    assert "pystray._win32" not in cmd
    assert check is True


def test_cli_entrypoint_can_run_as_main_script(monkeypatch):
    """CLI bootstrap should work when PyInstaller executes it as __main__."""
    repo_root = Path(__file__).resolve().parents[1]
    src_dir = repo_root / "src"
    entry_path = src_dir / "cogstash" / "cli" / "__main__.py"
    calls: list[tuple[str, object]] = []

    monkeypatch.syspath_prepend(str(src_dir))

    import cogstash.cli
    import cogstash.cli.windows

    monkeypatch.setattr(cogstash.cli.windows, "prepare_windows_cli_console", lambda: calls.append(("prepare", None)))
    monkeypatch.setattr(cogstash.cli, "cli_main", lambda argv: calls.append(("cli", argv)))
    monkeypatch.setattr(sys, "argv", [str(entry_path), "--help"])

    runpy.run_path(str(entry_path), run_name="__main__")

    assert calls == [("prepare", None), ("cli", ["--help"])]


def test_build_script_main_builds_ui_and_cli_targets_for_both(monkeypatch):
    """Default target=both should build UI onefile+onedir and CLI onefile."""
    module = _load_build_module()
    calls = []

    monkeypatch.setattr(module, "get_version", lambda: "1.2.3")
    monkeypatch.setattr(module, "convert_icon", lambda: None)
    monkeypatch.setattr(
        module,
        "run_pyinstaller",
        lambda **kwargs: calls.append(kwargs),
    )
    monkeypatch.setattr(module.sys, "argv", ["build.py", "--target", "both"])

    module.main()

    assert calls == [
        {"target": "ui", "bundle_mode": "onefile", "debug": False, "icon_path": None, "version": "1.2.3"},
        {"target": "ui", "bundle_mode": "onedir", "debug": False, "icon_path": None, "version": "1.2.3"},
        {"target": "cli", "bundle_mode": "onefile", "debug": False, "icon_path": None, "version": "1.2.3"},
    ]


def test_make_version_info_version_normalizes_dev_versions():
    """Inno Setup version info should receive a numeric 4-part version."""
    module = _load_build_installer_module()

    assert module.make_version_info_version("0.1.1.dev0+gf8d42d1c6.d20260328") == "0.1.1.0"
    assert module.make_version_info_version("1.2.3") == "1.2.3.0"
    assert module.make_version_info_version("7") == "7.0.0.0"


def test_release_workflow_builds_and_uploads_windows_installer():
    """Release workflow should compile and publish the Windows setup executable."""
    repo_root = Path(__file__).resolve().parents[1]
    workflow_path = repo_root / ".github" / "workflows" / "release.yml"

    content = workflow_path.read_text(encoding="utf-8")

    assert "Install Inno Setup" in content
    assert "choco install innosetup" in content
    assert "Build Windows installer" in content
    assert "uv run python scripts/build_installer.py" in content
    assert "ProgramFiles(x86)" in content
    assert "dist/CogStash-v*-setup.exe" in content
    assert "Smoke test onedir (Windows)" in content
    assert "dist\\CogStash-*-onedir\\CogStash-*-onedir.exe" in content
    assert "--help output unexpectedly contained Traceback" in content
    assert "--version output unexpectedly contained Traceback" in content


def test_release_workflow_uses_shared_artifact_contract():
    repo_root = Path(__file__).resolve().parents[1]
    workflow_path = repo_root / ".github" / "workflows" / "release.yml"

    content = workflow_path.read_text(encoding="utf-8")

    assert "sys.path.insert(0, \"scripts\")" in content
    assert "from _artifacts import get_executable_name" in content
    assert "from _artifacts import get_release_archive_name" in content
    assert "get_executable_name(target='ui', bundle_mode='onefile'" in content
    assert "get_executable_name(target='cli', bundle_mode='onefile'" in content
    assert "get_release_archive_name(tag=\"${{ github.ref_name }}\", platform_suffix=\"windows\")" in content
    assert "get_release_archive_name(tag=\"${{ github.ref_name }}\", platform_suffix=\"macos\")" in content
    assert "get_release_archive_name(tag=\"${{ github.ref_name }}\", platform_suffix=\"linux\")" in content
    assert "CogStash-${{ github.ref_name }}-windows.zip" not in content
    assert "CogStash-${{ github.ref_name }}-macos.zip" not in content
    assert "CogStash-${{ github.ref_name }}-linux.tar.gz" not in content


def test_release_workflow_uploads_ui_and_cli_artifacts():
    repo_root = Path(__file__).resolve().parents[1]
    workflow_path = repo_root / ".github" / "workflows" / "release.yml"
    workflow = workflow_path.read_text(encoding="utf-8")

    upload_steps = {
        match["step"]: {"name": match["artifact"], "path": match["path"].strip()}
        for match in re.finditer(
            r"- name: Upload (?P<step>UI|CLI) artifacts\r?\n"
            r"[ \t]+uses: actions/upload-artifact@v\d+\r?\n"
            r"[ \t]+with:\r?\n"
            r"[ \t]+name: (?P<artifact>[^\r\n]+)\r?\n"
            r"[ \t]+path: \|\r?\n"
            r"[ \t]+(?P<path>[^\r\n]+)",
            workflow,
        )
    }

    assert set(upload_steps) == {"UI", "CLI"}
    assert upload_steps["UI"]["name"] == "cogstash-${{ matrix.artifact_suffix }}-ui"
    assert upload_steps["CLI"]["name"] == "cogstash-${{ matrix.artifact_suffix }}-cli"
    assert upload_steps["UI"]["name"] != upload_steps["CLI"]["name"]
    assert upload_steps["UI"]["path"] == "dist/CogStash-${{ github.ref_name }}-${{ matrix.artifact_suffix }}*"
    assert upload_steps["CLI"]["path"] == "dist/CogStash-CLI-${{ github.ref_name }}-${{ matrix.artifact_suffix }}*"
    assert "CLI" not in upload_steps["UI"]["path"]
    assert "CLI" in upload_steps["CLI"]["path"]


def test_release_workflow_smoke_tests_ui_and_cli_on_unix():
    """Release workflow should smoke-test both entrypoints on macOS/Linux too."""
    repo_root = Path(__file__).resolve().parents[1]
    workflow_path = repo_root / ".github" / "workflows" / "release.yml"

    content = workflow_path.read_text(encoding="utf-8")
    ui_smoke_step = re.search(
        r"- name: Smoke test UI onedir \(Unix\)\r?\n"
        r"(?P<body>(?:[ \t]+.*(?:\r?\n|$))+?)"
        r"[ \t]+shell: bash",
        content,
    )

    assert "Install Linux UI smoke-test dependencies" in content
    assert "sudo apt-get install -y xvfb" in content
    assert "if: matrix.os == 'ubuntu-latest'" in content
    assert ui_smoke_step is not None
    ui_smoke_step_body = ui_smoke_step.group("body")
    assert "if: matrix.os != 'windows-latest'" in ui_smoke_step_body
    assert "find dist -maxdepth 2 -path 'dist/CogStash-*-onedir/CogStash-*-onedir'" in ui_smoke_step_body
    assert 'xvfb-run --auto-servernum "$binary" &' in ui_smoke_step_body
    assert any(line.strip() == '"$binary" &' for line in ui_smoke_step_body.splitlines())
    assert 'kill -0 "$pid" 2>/dev/null' in ui_smoke_step_body
    assert 'kill "$pid"' in ui_smoke_step_body
    assert 'wait "$pid"' in ui_smoke_step_body
    assert "exit 1" in ui_smoke_step_body
    assert "Smoke test CLI onefile (Unix)" in content


def test_installer_script_installs_cli_binary_without_shortcut():
    repo_root = Path(__file__).resolve().parents[1]
    iss_path = repo_root / "installer" / "windows" / "CogStash.iss"

    iss = iss_path.read_text(encoding="utf-8")
    assert "CogStash-CLI.exe" in iss
    assert "{app}\\bin" in iss
    # No Start Menu or Desktop shortcut entries for CogStash CLI
    assert 'Name: "{group}\\CogStash CLI"' not in iss
    assert 'Name: "{autodesktop}\\CogStash CLI"' not in iss


def test_compile_installer_resolves_paths_relative_to_caller(tmp_path, monkeypatch):
    module = _load_build_installer_module()
    calls = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module.subprocess, "run", lambda command, **kwargs: calls.append(command))
    module.compile_installer(compiler="iscc", iss_path=Path("installer/app.iss"), version="1.2.3",
                             source_dir=Path("build/payload"), output_dir=Path("dist"))
    assert f"/DSourceDir={tmp_path / 'build/payload'}" in calls[0]
    assert f"/DOutputDir={tmp_path / 'dist'}" in calls[0]
    assert calls[0][-1] == str(tmp_path / "installer/app.iss")


@pytest.mark.parametrize("version,expected", [
    ("0.1.dev1+g816208cd7", "0.1.0.1"),
    ("1.2.3+g123456789", "1.2.3.0"),
    ("1.2.3rc2", "1.2.3.2"),
    ("1.2.3.post4", "1.2.3.4"),
    ("1.2.3.4", "1.2.3.4"),
])
def test_windows_version_excludes_git_hash_and_handles_short_releases(version, expected):
    assert _load_build_installer_module().make_version_info_version(version) == expected


def test_windows_version_rejects_out_of_range_components():
    with pytest.raises(ValueError, match="65535"):
        _load_build_installer_module().make_version_info_version("65536.0.0")
