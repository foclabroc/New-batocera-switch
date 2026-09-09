#!/usr/bin/python
# -*- coding: utf-8 -*-
import re
import sys
import os
import subprocess
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


def _detect_batocera_version() -> int | None:
    """Reprend la méthode utilisée ailleurs dans tes scripts d'install :
    `batocera-es-swissknife --version` + extraction du numéro majeur en tête
    de chaîne. Renvoie None si indisponible/illisible — dans ce cas on
    retombe sur l'ancienne API par sécurité."""
    try:
        result = subprocess.run(
            ["batocera-es-swissknife", "--version"],
            capture_output=True, text=True, check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None

    m = re.search(r"^\s*(\d+)", result.stdout)
    if not m:
        return None
    return int(m.group(1))


def run_new_api() -> None:
    """Batocera > 43.1 — archi batocera_launch. Testée et fonctionnelle en v44."""
    import runpy

    ROM_PATH = rom
    EMULATOR_OVERRIDE = emulator_name or None

    try:
        from generators.edenGenerator import EdenGenerator
    except Exception as e:
        print(f'[SWITCH] Failed importing EdenGenerator: {e}', file=sys.stderr)
        raise
    try:
        from generators.ryujinxGenerator import RyujinxGenerator
    except Exception as e:
        print(f'[SWITCH] Failed importing RyujinxGenerator: {e}', file=sys.stderr)
        raise

    import configgen.generators.importer
    _original_get_generator = configgen.generators.importer.get_generator

    def switch_get_generator(emulator: str, core: str | None = None):
        rom_name = os.path.basename(ROM_PATH)
        if rom_name == 'ryujinx_config.xci_config':
            emulator = 'ryujinx-emu'
        print(f'[SWITCH] emulator={emulator}', file=sys.stderr)
        print(f'[SWITCH] rom={rom_name}', file=sys.stderr)
        if emulator in YUZU_LIKE:
            return EdenGenerator()
        if emulator == 'ryujinx-emu':
            return RyujinxGenerator()
        return _original_get_generator(emulator, core)

    configgen.generators.importer.get_generator = switch_get_generator

    try:
        import configgen.launch
        configgen.launch.get_generator = switch_get_generator
    except ImportError:
        pass

    try:
        import configgen.emulatorlauncher
        configgen.emulatorlauncher.get_generator = switch_get_generator
    except ImportError:
        pass

    from batocera_launch.config import defaults
    _original_load_system_defaults = defaults.load_system_defaults

    def switch_load_system_defaults(system_name: str):
        if SWITCH_DEFAULTS.exists() and SWITCH_ARCH.exists():
            data = defaults.load_defaults(system_name, SWITCH_DEFAULTS, SWITCH_ARCH) or {}
            result = {'emulator': data.get('emulator'), 'core': data.get('core')}
            if 'options' in data:
                result.update(data['options'])
            emulator = EMULATOR_OVERRIDE or result.get('emulator')
            if emulator == 'ryujinx-emu':
                result['hud_support'] = False
            else:
                result.setdefault('hud_support', True)
            return result

        result = _original_load_system_defaults(system_name)
        emulator = EMULATOR_OVERRIDE or result.get('emulator')
        if emulator == 'ryujinx-emu':
            result['hud_support'] = False
        else:
            result.setdefault('hud_support', True)
        return result

    defaults.load_system_defaults = switch_load_system_defaults

    runpy.run_module('batocera_launch', run_name='__main__')


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
    version = _detect_batocera_version()
    if version is not None and version >= 44:
        run_new_api()
    else:
        run_old_api()
