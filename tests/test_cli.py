import subprocess
import sys


def test_cli_health_runs() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "usagedash.cli", "health"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "config" in proc.stdout
