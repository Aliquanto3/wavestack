"""The one-command installers (install.bat, install.ps1, install.sh) stay in sync with
README.md's Qwen URL, and install.ps1's dry run / idempotent paths behave as documented.

No installer here ever touches the real `uv`, Documents or %LOCALAPPDATA%\\WaveStack: every
PowerShell run below passes -InstallDir/-DataDir pointing at pytest's own tmp_path, and the
network calls (uv install, git clone, model download) are never reached because the tests
only exercise -DryRun or the already-installed, idempotent branch.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

import pytest

from wavestack import config

ROOT = config.repo_root()
README_TEXT = (ROOT / "README.md").read_text(encoding="utf-8")
QWEN_URL_RE = re.compile(
    r"https://huggingface\.co/unsloth/Qwen3\.5-2B-GGUF/resolve/main/[^\s)\"']+"
)


def _qwen_url(text: str) -> str:
    match = QWEN_URL_RE.search(text)
    assert match, "URL du modele Qwen introuvable"
    return match.group(0)


README_QWEN_URL = _qwen_url(README_TEXT)


@pytest.mark.parametrize("name", ["install.ps1", "install.sh"])
def test_installer_reuses_readme_qwen_url(name: str) -> None:
    text = (ROOT / name).read_text(encoding="utf-8")
    assert _qwen_url(text) == README_QWEN_URL


def test_install_bat_delegates_to_install_ps1() -> None:
    text = (ROOT / "install.bat").read_text(encoding="utf-8")
    assert "install.ps1" in text
    assert "-NoProfile" in text
    assert "-ExecutionPolicy Bypass" in text


def test_install_sh_syntax() -> None:
    if not shutil.which("bash"):
        pytest.skip("bash indisponible sur ce poste")
    # The resolved path: Windows looks in System32 (WSL bash) before PATH.
    subprocess.run([shutil.which("bash"), "-n", str(ROOT / "install.sh")], check=True)


@pytest.mark.skipif(sys.platform != "win32", reason="install.ps1 cible Windows")
def test_install_ps1_dry_run_resolves_overridden_paths(tmp_path) -> None:
    install_dir = tmp_path / "project"
    data_dir = tmp_path / "data"
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "install.ps1"),
            "-InstallDir",
            str(install_dir),
            "-DataDir",
            str(data_dir),
            "-DryRun",
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert str(install_dir) in result.stdout
    assert str(data_dir) in result.stdout
    assert "Qwen3.5-2B-Q4_K_M.gguf" in result.stdout
    # Mode a blanc : aucun dossier ni fichier cree.
    assert not install_dir.exists()
    assert not data_dir.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="install.ps1 cible Windows")
@pytest.mark.skipif(
    shutil.which("uv") is None, reason="uv absent : eviterait un telechargement reel"
)
def test_install_ps1_is_idempotent_when_already_installed(tmp_path) -> None:
    install_dir = tmp_path / "project"
    data_dir = tmp_path / "data"
    (data_dir / "models").mkdir(parents=True)
    install_dir.mkdir()
    (install_dir / "pyproject.toml").write_text("[project]\nname = 'fake'\n", encoding="utf-8")
    (data_dir / "models" / "Qwen3.5-2B-Q4_K_M.gguf").write_bytes(
        b"fake model, not the real 1.3 GB file"
    )

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "install.ps1"),
            "-InstallDir",
            str(install_dir),
            "-DataDir",
            str(data_dir),
            "-NoLaunch",
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    assert "pas de nouveau clone" in result.stdout
    assert "pas de nouveau telechargement" in result.stdout


def test_install_sh_dry_run_creates_nothing(tmp_path) -> None:
    if not shutil.which("bash"):
        pytest.skip("bash indisponible sur ce poste")
    env = {
        **os.environ,
        "WAVESTACK_INSTALL_DIR": (tmp_path / "project").as_posix(),
        "WAVESTACK_DATA_DIR": (tmp_path / "data").as_posix(),
        "WAVESTACK_DRY_RUN": "1",
    }
    result = subprocess.run(
        [shutil.which("bash"), (ROOT / "install.sh").as_posix()],
        capture_output=True,
        text=True,
        check=True,
        env=env,
        timeout=30,
    )
    assert "Qwen3.5-2B-Q4_K_M.gguf" in result.stdout
    assert not (tmp_path / "project").exists()
    assert not (tmp_path / "data").exists()


@pytest.mark.skipif(sys.platform != "win32", reason="install.ps1 cible Windows")
@pytest.mark.skipif(
    shutil.which("uv") is None, reason="uv absent : eviterait un telechargement reel"
)
def test_install_ps1_stops_when_git_clone_fails(tmp_path) -> None:
    # A failing native command must stop the script before the 1.3 GB model download.
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "git.cmd").write_text("@exit /b 128\r\n", encoding="ascii")
    env = {**os.environ, "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"}
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "install.ps1"),
            "-InstallDir",
            str(tmp_path / "project"),
            "-DataDir",
            str(tmp_path / "data"),
            "-NoLaunch",
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert result.returncode != 0
    assert "git clone a echoue" in result.stdout + result.stderr
    assert not (tmp_path / "data").exists()


MINICPM_URL = (
    "https://huggingface.co/openbmb/MiniCPM5-2B-GGUF/resolve/"
    "2079a22f3beaa4e306449978533478fe0522f4b3/MiniCPM5-2B-Q4_K_M.gguf"
)


@pytest.mark.parametrize("name", ["install.ps1", "install.sh", "docs/installation.md"])
def test_minicpm_url_is_the_same_everywhere(name: str) -> None:
    assert MINICPM_URL in (ROOT / name).read_text(encoding="utf-8")


def test_default_model_file_matches_the_installers() -> None:
    assert f"'{config.DEFAULT_MODEL_FILE}'" in (ROOT / "install.ps1").read_text(encoding="utf-8")
    assert f'"{config.DEFAULT_MODEL_FILE}"' in (ROOT / "install.sh").read_text(encoding="utf-8")


def _sh_dry_run(tmp_path, **extra: str) -> str:
    env = {
        **os.environ,
        "WAVESTACK_INSTALL_DIR": (tmp_path / "project").as_posix(),
        "WAVESTACK_DATA_DIR": (tmp_path / "data").as_posix(),
        "WAVESTACK_DRY_RUN": "1",
        **extra,
    }
    result = subprocess.run(
        [shutil.which("bash"), (ROOT / "install.sh").as_posix()],
        capture_output=True,
        text=True,
        check=True,
        env=env,
        timeout=30,
    )
    assert not (tmp_path / "data").exists()
    return result.stdout


def test_install_sh_minicpm_only_on_request(tmp_path) -> None:
    if not shutil.which("bash"):
        pytest.skip("bash indisponible sur ce poste")
    assert "MiniCPM5" not in _sh_dry_run(tmp_path)
    assert "MiniCPM5-2B-Q4_K_M.gguf" in _sh_dry_run(tmp_path, WAVESTACK_WITH_MINICPM="1")


@pytest.mark.skipif(sys.platform != "win32", reason="install.ps1 cible Windows")
@pytest.mark.parametrize("option", [[], ["-WithMiniCPM"]])
def test_install_ps1_minicpm_dry_run(tmp_path, option) -> None:
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "install.ps1"),
            "-InstallDir",
            str(tmp_path / "project"),
            "-DataDir",
            str(tmp_path / "data"),
            "-DryRun",
            *option,
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert ("MiniCPM5-2B-Q4_K_M.gguf" in result.stdout) is bool(option)
    assert not (tmp_path / "data").exists()
