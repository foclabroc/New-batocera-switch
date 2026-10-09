#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""Point d'entrée du pack Switch appelé par EmulationStation.

- Batocera avec configgen (< 44 et premières 44-dev) : ancien switchlauncher.py
- Batocera sans configgen : batocera-launch, avec les émulateurs Switch
  déclarés comme plugins (switch_launch-1.0.dist-info/entry_points.txt)
"""
import importlib.util
import os
import runpy
import sys
from pathlib import Path

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
CONFIGGEN_DIR = HERE.parent / "configgen"
SWITCH_DEFAULTS = CONFIGGEN_DIR / "configgen-defaults.yml"
SWITCH_ARCH = CONFIGGEN_DIR / "configgen-defaults-arch.yml"


def _has_configgen() -> bool:
    try:
        return importlib.util.find_spec("configgen") is not None
    except (ImportError, ValueError):
        return False


def _fix_config_apps_emulator() -> None:
    # L'app de config Ryujinx doit toujours partir sur Ryujinx
    if "-rom" in sys.argv and "-emulator" in sys.argv:
        if os.path.basename(sys.argv[sys.argv.index("-rom") + 1]) == "ryujinx_config.xci_config":
            sys.argv[sys.argv.index("-emulator") + 1] = "ryujinx-emu"


def run_batocera_launch() -> None:
    # Rend nos plugins visibles par importlib.metadata (entry points)
    sys.path.insert(0, str(HERE))
    _fix_config_apps_emulator()

    # batocera-launch n'a pas de defaults pour le système "switch" : on fournit les nôtres
    from batocera_launch.config import config as config_mod, defaults

    original = defaults.load_system_defaults

    def load_system_defaults(system_name: str, /):
        if system_name != "switch" or not SWITCH_DEFAULTS.exists():
            return original(system_name)
        data = defaults.load_defaults(system_name, SWITCH_DEFAULTS, SWITCH_ARCH) or {}
        result = {"emulator": data.get("emulator"), "core": data.get("core")}
        result.update(data.get("options") or {})
        result["hud_support"] = True  # désactivé côté Ryujinx dans sa classe
        return result

    defaults.load_system_defaults = load_system_defaults
    config_mod.load_system_defaults = load_system_defaults

    from batocera_launch.cli.main import main
    main()


def run_configgen() -> None:
    sys.path.insert(0, str(CONFIGGEN_DIR))
    sys.argv[0] = str(CONFIGGEN_DIR / "switchlauncher.py")
    runpy.run_path(sys.argv[0], run_name="__main__")


if __name__ == "__main__":
    if _has_configgen():
        run_configgen()
    else:
        run_batocera_launch()
