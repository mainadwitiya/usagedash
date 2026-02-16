from pathlib import Path

from usagedash.config import load_config
from usagedash.snapshot import build_snapshot, write_snapshot_files


def test_snapshot_write(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "config.toml")
    cfg.general.state_file = str(tmp_path / "latest.json")
    cfg.general.windows_state_path = str(tmp_path / "mirror.json")

    snap = build_snapshot(cfg)
    write_snapshot_files(cfg, snap)

    assert Path(cfg.general.state_file).exists()
    assert Path(cfg.general.windows_state_path).exists()
