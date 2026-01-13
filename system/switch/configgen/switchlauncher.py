#!/usr/bin/python
# -*- coding: utf-8 -*-
import re
import sys
import yaml

from importlib import import_module
import configgen
from configgen.Emulator import Emulator, _dict_merge, _load_defaults, _load_system_config
from configgen.emulatorlauncher import launch
from configgen.generators import get_generator

from typing import TYPE_CHECKING, Any

from pathlib import Path


def _new_get_generator(emulator: str):
    
    yuzuemu = {}
    yuzuemu['eden-emu'] = 1
    yuzuemu['citron-emu'] = 1
    yuzuemu['eden-pgo'] = 1


    if emulator in yuzuemu:
        from generators.edenGenerator import EdenGenerator
        return EdenGenerator()

    if emulator == 'ryujinx-emu':
        from generators.ryujinxGenerator import RyujinxMainlineGenerator
        return RyujinxMainlineGenerator()

    #fallback to batocera generators
    return get_generator(emulator)
    
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

    data: dict[str, Any] = {
        "emulator": defaults.get("emulator"),
        "core": defaults.get("core"),
    }

    if "options" in defaults:
        _dict_merge(data, defaults["options"])

    return data



#configgen.Emulator._load_system_config = _new_load_system_config
configgen.emulatorlauncher.get_generator = _new_get_generator
configgen.Emulator._load_system_config = _new_load_system_config

if __name__ == "__main__":
    sys.argv[0] = re.sub(r"(-script\.pyw|\.exe)?$", "", sys.argv[0])
    sys.exit(launch())
