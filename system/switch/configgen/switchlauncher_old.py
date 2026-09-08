#!/usr/bin/python
# -*- coding: utf-8 -*-
import re
import sys
import os
import yaml

from importlib import import_module
import configgen
from configgen.Emulator import Emulator, _dict_merge, _load_defaults, _load_system_config
from configgen.emulatorlauncher import launch
from configgen.generators import get_generator

from typing import TYPE_CHECKING, Any

from pathlib import Path

rom = None
if "-rom" in sys.argv:
    rom = sys.argv[sys.argv.index("-rom") + 1]
if "-emulator" in sys.argv:
    emulator_name = sys.argv[sys.argv.index("-emulator") + 1]

def _new_get_generator(emulator: str, core: str | None = None):
    
    yuzuemu = {}
    yuzuemu['eden-emu'] = 1
    yuzuemu['citron-emu'] = 1
    yuzuemu['eden-pgo'] = 1
    yuzuemu['eden-nightly'] = 1

    rom_nameq = os.path.basename(rom)
    if rom_nameq == 'ryujinx_config.xci_config':
        emulator = 'ryujinx-emu'
   
    print(f"Selected emulator: {emulator}", file=sys.stderr)    
    print(f"Selected Rom : {rom_nameq}", file=sys.stderr)    

    if emulator in yuzuemu:
        from generators.edenGenerator import EdenGenerator
        return EdenGenerator()

    if emulator == 'ryujinx-emu':
        from generators.ryujinxGenerator import RyujinxGenerator
        return RyujinxGenerator()

    #fallback to batocera generators
    return get_generator(emulator, core)
    
from configgen.batoceraPaths import DEFAULTS_DIR

def _new_load_system_config(system_name: str, /) -> dict[str, Any]:
    switch_defaults = Path("/userdata/system/switch/configgen/configgen-defaults.yml")
    switch_arch = Path("/userdata/system/switch/configgen/configgen-defaults-arch.yml")

    # Utiliser Switch si dispo
    if switch_defaults.exists() and switch_arch.exists():
        defaults = _load_defaults(system_name, switch_defaults, switch_arch)
    else:
        # Fallback Batocera original
        defaults = _load_defaults(
            system_name,
            DEFAULTS_DIR / "configgen-defaults.yml",
            DEFAULTS_DIR / "configgen-defaults-arch.yml",
        )

    if emulator_name == "ryujinx-emu":
        defaults.setdefault("options", {})["hud_support"] = False
    else:
        defaults.setdefault("options", {})["hud_support"] = True
    data: dict[str, Any] = {
        "emulator": defaults.get("emulator"),
        "core": defaults.get("core"),
    }

    if "options" in defaults:
        _dict_merge(data, defaults["options"])

    return data

configgen.emulatorlauncher.get_generator = _new_get_generator
configgen.Emulator._load_system_config = _new_load_system_config

if __name__ == "__main__":
    sys.argv[0] = re.sub(r"(-script\.pyw|\.exe)?$", "", sys.argv[0])
    sys.exit(launch())