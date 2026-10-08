from __future__ import annotations

from pathlib import Path

from batocera_common.paths import BIOS, CACHE, CONFIGS, HOME, ROMS, SAVES, SCREENSHOTS, USERDATA  # noqa: F401


def mkdir_if_not_exists(path: Path, /) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)
