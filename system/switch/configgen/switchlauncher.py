#!/usr/bin/python
# -*- coding: utf-8 -*-
import re
import sys
import os
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

rom = sys.argv[sys.argv.index("-rom") + 1] if "-rom" in sys.argv else ""
emulator_name = sys.argv[sys.argv.index("-emulator") + 1] if "-emulator" in sys.argv else ""

YUZU_LIKE = {'eden-emu', 'citron-emu', 'eden-pgo', 'eden-nightly'}
SWITCH_DEFAULTS = Path("/userdata/system/switch/configgen/configgen-defaults.yml")
SWITCH_ARCH = Path("/userdata/system/switch/configgen/configgen-defaults-arch.yml")


def _log_selection(emulator: str) -> str:
    rom_name = os.path.basename(rom)
    if rom_name == 'ryujinx_config.xci_config':
        emulator = 'ryujinx-emu'
    print(f"Selected emulator: {emulator}", file=sys.stderr)
    print(f"Selected Rom : {rom_name}", file=sys.stderr)
    return emulator


# Détection d'architecture interne : Batocera >= 44 a migré configgen vers le
# paquet batocera_launch. S'il est importable, on est sur la nouvelle archi.
try:
    import batocera_launch  # noqa: F401
    NEW_API = True
except ImportError:
    NEW_API = False


def run_new_api() -> None:
    """Batocera > 43.1 (>= 44) — nouvelle archi batocera_launch."""
    import argparse
    import runpy
    import configgen.generators.importer
    from batocera_launch import Emulator
    from batocera_launch.Emulator import _load_defaults, _dict_merge
    from generators.edenGenerator import EdenGenerator
    from generators.ryujinxGenerator import RyujinxGenerator

    _original_get_generator = configgen.generators.importer.get_generator

    def _new_get_generator(emulator: str, core: str | None = None):
        emulator = _log_selection(emulator)
        if emulator in YUZU_LIKE:
            return EdenGenerator()
        if emulator == 'ryujinx-emu':
            return RyujinxGenerator()
        return _original_get_generator(emulator, core)

    configgen.generators.importer.get_generator = _new_get_generator

    _original_emulator_init = Emulator.__init__

    def _new_emulator_init(self, args: Any, original_rom: Path, /):
        _original_emulator_init(self, args, original_rom)
        if SWITCH_DEFAULTS.exists() and SWITCH_ARCH.exists():
            system_name = getattr(args, 'system', 'switch')
            defaults = _load_defaults(system_name, SWITCH_DEFAULTS, SWITCH_ARCH)
            if "options" in defaults:
                _dict_merge(self.config, defaults["options"])
        self.config["hud_support"] = self.config.get('emulator', '') != "ryujinx-emu"

    Emulator.__init__ = _new_emulator_init

    parser = argparse.ArgumentParser()
    parser.add_argument("-rom", type=Path, required=True)
    parser.add_argument("-system", type=str, required=True)
    parser.add_argument("-emulator", type=str, default="default")
    parser.add_argument("-core", type=str, default="default")
    parser.add_argument("-players", type=str, default="")
    parser.parse_known_args(sys.argv[1:])

    try:
        runpy.run_module("batocera_launch", run_name="__main__")
    except Exception as e:
        print(f"Launcher handoff error: {e}", file=sys.stderr)
        sys.exit(1)


def run_old_api() -> None:
    """Batocera < 44 — ancienne archi configgen."""
    import configgen
    from configgen.Emulator import _dict_merge, _load_defaults
    from configgen.emulatorlauncher import launch
    from configgen.generators import get_generator
    from configgen.batoceraPaths import DEFAULTS_DIR

    def _new_get_generator(emulator: str, core: str | None = None):
        emulator = _log_selection(emulator)
        if emulator in YUZU_LIKE:
            from generators.edenGenerator import EdenGenerator
            return EdenGenerator()
        if emulator == 'ryujinx-emu':
            from generators.ryujinxGenerator import RyujinxGenerator
            return RyujinxGenerator()
        return get_generator(emulator, core)

    def _new_load_system_config(system_name: str, /) -> dict[str, Any]:
        if SWITCH_DEFAULTS.exists() and SWITCH_ARCH.exists():
            defaults = _load_defaults(system_name, SWITCH_DEFAULTS, SWITCH_ARCH)
        else:
            defaults = _load_defaults(
                system_name,
                DEFAULTS_DIR / "configgen-defaults.yml",
                DEFAULTS_DIR / "configgen-defaults-arch.yml",
            )
        defaults.setdefault("options", {})["hud_support"] = emulator_name != "ryujinx-emu"
        data: dict[str, Any] = {
            "emulator": defaults.get("emulator"),
            "core": defaults.get("core"),
        }
        if "options" in defaults:
            _dict_merge(data, defaults["options"])
        return data

    configgen.emulatorlauncher.get_generator = _new_get_generator
    configgen.Emulator._load_system_config = _new_load_system_config

    sys.argv[0] = re.sub(r"(-script\.pyw|\.exe)?$", "", sys.argv[0])
    sys.exit(launch())


if __name__ == "__main__":
    if NEW_API:
        run_new_api()
    else:
        run_old_api()
