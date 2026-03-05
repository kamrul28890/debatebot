import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_setup_selected_mode_help() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/setup_selected_mode.py", "--help"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0
    assert "--combo" in completed.stdout
    assert "azure_robotic" in completed.stdout
    assert "qwen_cloned" in completed.stdout
    assert "--skip-cache" not in completed.stdout
    assert "--force-cache" not in completed.stdout
