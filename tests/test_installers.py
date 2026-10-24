"""The one-command installers (install.bat, install.ps1, install.sh) stay in sync with
README.md's Qwen URL, and install.ps1's dry run / idempotent paths behave as documented.

No installer here ever touches the real `uv`, Documents or %LOCALAPPDATA%\\WaveStack: every
PowerShell run below passes -InstallDir/-DataDir pointing at pytest's own tmp_path, and the
network calls (uv install, git clone, model download) are never reached because the tests
only exercise -DryRun or the already-installed, idempotent branch.
"""

from __future__ import annotations

import hashlib
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


OPTIONAL_MODELS = {
    "qwen3.5-0.8b": (
        "https://huggingface.co/unsloth/Qwen3.5-0.8B-GGUF/resolve/"
        "6ab461498e2023f6e3c1baea90a8f0fe38ab64d0/Qwen3.5-0.8B-Q4_K_M.gguf",
        "Qwen3.5-0.8B-Q4_K_M.gguf",
        "bd258782e35f7f458f8aced1adc053e6e92e89bc735ba3be89d38a06121dc517",
    ),
    "minicpm5": (
        "https://huggingface.co/openbmb/MiniCPM5-2B-GGUF/resolve/"
        "2079a22f3beaa4e306449978533478fe0522f4b3/MiniCPM5-2B-Q4_K_M.gguf",
        "MiniCPM5-2B-Q4_K_M.gguf",
        "ec2d5801640099e97d8d7e8003ad4d81f336e757811f03a26173dddf386602fd",
    ),
    "granite-4.0-350m": (
        "https://huggingface.co/ibm-granite/granite-4.0-350m-GGUF/resolve/"
        "b8208a86a58427e1739265318028eb5895b74bf2/granite-4.0-350m-Q4_K_M.gguf",
        "granite-4.0-350m-Q4_K_M.gguf",
        "771c588a49607f274a2bba3185733607ebe6f74b996ab90e2d6bee0d98bcec52",
    ),
    "granite-4.0-1b": (
        "https://huggingface.co/ibm-granite/granite-4.0-1b-GGUF/resolve/"
        "b27c2fe3f211b7f44e80fa620177aea371099aaa/granite-4.0-1b-Q4_K_M.gguf",
        "granite-4.0-1b-Q4_K_M.gguf",
        "22ec0f9cc99a90185312de3c882c84e7bd6789bdd050389844380a01a831d7f1",
    ),
}
VALID_IDS = ", ".join(OPTIONAL_MODELS)


@pytest.mark.parametrize("model_id", list(OPTIONAL_MODELS))
@pytest.mark.parametrize("name", ["install.ps1", "install.sh", "docs/installation.md"])
def test_optional_model_url_is_the_same_everywhere(name: str, model_id: str) -> None:
    url, _file, _sha = OPTIONAL_MODELS[model_id]
    assert url in (ROOT / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("model_id", list(OPTIONAL_MODELS))
@pytest.mark.parametrize("name", ["install.ps1", "install.sh"])
def test_optional_model_row_is_complete(name: str, model_id: str) -> None:
    _url, file, sha = OPTIONAL_MODELS[model_id]
    text = (ROOT / name).read_text(encoding="utf-8")
    assert model_id in text
    assert file in text
    assert sha in text


def test_default_model_file_matches_the_installers() -> None:
    assert f"'{config.DEFAULT_MODEL_FILE}'" in (ROOT / "install.ps1").read_text(encoding="utf-8")
    assert f'"{config.DEFAULT_MODEL_FILE}"' in (ROOT / "install.sh").read_text(encoding="utf-8")


def _clean_env() -> dict[str, str]:
    """os.environ without the WAVESTACK_* variables a developer may have set on the machine."""
    return {k: v for k, v in os.environ.items() if not k.upper().startswith("WAVESTACK_")}


def _sh(tmp_path, *, dry_run: bool = True, **extra: str) -> subprocess.CompletedProcess:
    env = {
        **_clean_env(),
        "WAVESTACK_INSTALL_DIR": (tmp_path / "project").as_posix(),
        "WAVESTACK_DATA_DIR": (tmp_path / "data").as_posix(),
        **({"WAVESTACK_DRY_RUN": "1"} if dry_run else {}),
        **extra,
    }
    return subprocess.run(
        [shutil.which("bash"), (ROOT / "install.sh").as_posix()],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def _ps(tmp_path, *option: str, **env_extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
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
            *option,
        ],
        capture_output=True,
        text=True,
        env={**_clean_env(), **env_extra},
        timeout=30,
    )


needs_bash = pytest.mark.skipif(not shutil.which("bash"), reason="bash indisponible sur ce poste")
needs_windows = pytest.mark.skipif(sys.platform != "win32", reason="install.ps1 cible Windows")


@needs_bash
def test_install_sh_models_only_on_request(tmp_path) -> None:
    assert "MiniCPM5" not in _sh(tmp_path).stdout
    assert "Qwen3.5-0.8B" not in _sh(tmp_path).stdout
    both = _sh(tmp_path, WAVESTACK_MODELS="qwen3.5-0.8b,minicpm5")
    assert both.returncode == 0
    assert "Qwen3.5-0.8B-Q4_K_M.gguf" in both.stdout
    assert "MiniCPM5-2B-Q4_K_M.gguf" in both.stdout
    assert not (tmp_path / "data").exists()


@needs_bash
def test_install_sh_minicpm_alias(tmp_path) -> None:
    out = _sh(tmp_path, WAVESTACK_WITH_MINICPM="1").stdout
    assert "MiniCPM5-2B-Q4_K_M.gguf" in out
    assert "Qwen3.5-0.8B" not in out
    both = _sh(tmp_path, WAVESTACK_WITH_MINICPM="1", WAVESTACK_MODELS="minicpm5").stdout
    assert both.count("MiniCPM5-2B-Q4_K_M.gguf") == 1


@needs_bash
@pytest.mark.parametrize("dry_run", [True, False])
def test_install_sh_unknown_model_stops_before_anything(tmp_path, dry_run) -> None:
    result = _sh(tmp_path, dry_run=dry_run, WAVESTACK_MODELS="qwen3.5-0.8b,inconnu")
    assert result.returncode != 0
    assert "inconnu" in result.stderr
    assert VALID_IDS in result.stderr
    assert not (tmp_path / "data").exists()
    assert not (tmp_path / "project").exists()


@needs_bash
def test_install_sh_model_id_is_not_a_pattern(tmp_path) -> None:
    result = _sh(tmp_path, WAVESTACK_MODELS="qwen3[.]5-0.8b")
    assert result.returncode != 0
    assert "inconnu" in result.stderr


@needs_bash
def test_install_sh_models_list_prints_the_table_and_stops(tmp_path) -> None:
    result = _sh(tmp_path, dry_run=False, WAVESTACK_MODELS="list")
    assert result.returncode == 0
    for model_id, (_url, file, _sha) in OPTIONAL_MODELS.items():
        assert model_id in result.stdout
        assert file in result.stdout
    assert "Apache-2.0" in result.stdout
    assert not (tmp_path / "data").exists()
    assert not (tmp_path / "project").exists()


@needs_windows
@pytest.mark.parametrize("option", [[], ["-WithMiniCPM"], ["-Models", "qwen3.5-0.8b,minicpm5"]])
def test_install_ps1_models_dry_run(tmp_path, option) -> None:
    result = _ps(tmp_path, "-DryRun", *option)
    assert result.returncode == 0, result.stderr
    assert ("MiniCPM5-2B-Q4_K_M.gguf" in result.stdout) is bool(option)
    assert ("Qwen3.5-0.8B-Q4_K_M.gguf" in result.stdout) is ("-Models" in option)
    assert not (tmp_path / "data").exists()


@needs_windows
def test_install_ps1_models_as_a_powershell_array(tmp_path) -> None:
    # `.\install.ps1 -Models a,b` typed in a PowerShell session binds an array, not a string.
    project, data = tmp_path / "project", tmp_path / "data"
    command = (
        f"& '{ROOT / 'install.ps1'}' -InstallDir '{project}' -DataDir '{data}' -DryRun "
        "-Models qwen3.5-0.8b,minicpm5"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        capture_output=True,
        text=True,
        env=_clean_env(),
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "Qwen3.5-0.8B-Q4_K_M.gguf" in result.stdout
    assert "MiniCPM5-2B-Q4_K_M.gguf" in result.stdout
    assert not data.exists()


@needs_windows
def test_install_ps1_models_from_environment(tmp_path) -> None:
    result = _ps(tmp_path, "-DryRun", WAVESTACK_MODELS="qwen3.5-0.8b")
    assert result.returncode == 0, result.stderr
    assert "Qwen3.5-0.8B-Q4_K_M.gguf" in result.stdout
    assert "MiniCPM5" not in result.stdout


@needs_windows
@pytest.mark.parametrize("option", [["-DryRun"], []])
def test_install_ps1_unknown_model_stops_before_anything(tmp_path, option) -> None:
    result = _ps(tmp_path, "-Models", "inconnu", *option)
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "inconnu" in output
    assert VALID_IDS in " ".join(output.split())
    assert not (tmp_path / "data").exists()
    assert not (tmp_path / "project").exists()


@needs_windows
def test_install_ps1_models_list_prints_the_table_and_stops(tmp_path) -> None:
    result = _ps(tmp_path, "-Models", "list")
    assert result.returncode == 0, result.stderr
    for model_id, (_url, file, _sha) in OPTIONAL_MODELS.items():
        assert model_id in result.stdout
        assert file in result.stdout
    assert not (tmp_path / "data").exists()
    assert not (tmp_path / "project").exists()


# -- Verification d'empreinte, sur un petit fichier local (aucun reseau).
GOOD_BYTES = b"petit faux modele"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _function_source(text: str, start: str) -> str:
    """The function whose definition line starts with `start`, up to its closing brace."""
    lines = text.splitlines()
    first = next(i for i, line in enumerate(lines) if line.strip().startswith(start))
    indent = lines[first][: len(lines[first]) - len(lines[first].lstrip())]
    last = next(i for i in range(first + 1, len(lines)) if lines[i] == indent + "}")
    return "\n".join(lines[first : last + 1])


@needs_bash
@pytest.mark.parametrize("good", [True, False])
def test_install_sh_verify_sha256(tmp_path, good) -> None:
    func = _function_source((ROOT / "install.sh").read_text(encoding="utf-8"), "verify_sha256()")
    model = tmp_path / "m.gguf.part"
    model.write_bytes(GOOD_BYTES)
    expected = _sha256(GOOD_BYTES if good else b"autre contenu")
    result = subprocess.run(
        [
            shutil.which("bash"),
            "-c",
            f'{func}\nverify_sha256 "$1" "$2"',
            "bash",
            model.as_posix(),
            expected,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if good:
        assert result.returncode == 0
        assert model.exists()
    else:
        assert result.returncode != 0
        assert "non conforme" in result.stderr
        assert not model.exists()


@needs_windows
@pytest.mark.parametrize("good", [True, False])
def test_install_ps1_verify_hash(tmp_path, good) -> None:
    func = _function_source(
        (ROOT / "install.ps1").read_text(encoding="utf-8"), "function Test-ModelHash"
    )
    model = tmp_path / "m.gguf.part"
    model.write_bytes(GOOD_BYTES)
    expected = _sha256(GOOD_BYTES if good else b"autre contenu").upper()
    script = tmp_path / "check.ps1"
    script.write_text(
        f"$ErrorActionPreference = 'Stop'\n{func}\nTest-ModelHash '{model}' '{expected}'\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if good:
        assert result.returncode == 0, result.stderr
        assert model.exists()
    else:
        assert result.returncode != 0
        assert "non conforme" in result.stdout + result.stderr
        assert not model.exists()
