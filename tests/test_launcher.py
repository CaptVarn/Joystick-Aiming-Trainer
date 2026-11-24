import shutil
import subprocess
import sys
from pathlib import Path

LAUNCHER = Path(__file__).resolve().parents[1] / "main.py"


def test_checkout_launcher_finds_source_without_an_editable_install(tmp_path):
    result = subprocess.run(
        [sys.executable, "-I", "-S", str(LAUNCHER), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "Missing dependency: pygame" in result.stderr
    assert "python -m pip install ." in result.stderr


def test_launcher_reports_an_incomplete_download(tmp_path):
    launcher = shutil.copy(LAUNCHER, tmp_path)
    result = subprocess.run(
        [sys.executable, "-I", "-S", launcher], capture_output=True, text=True, check=False
    )
    assert result.returncode == 1
    assert "Clone or download the full repository." in result.stderr
