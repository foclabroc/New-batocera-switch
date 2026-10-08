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
    """Batocera > 43.1."""
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


def _has_real_configgen() -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec("configgen") is not None
    except (ImportError, ValueError):
        return False


def _switch_load_system_defaults(original):
    """Charge les defaults du pack switch (le système switch n'existe plus côté Batocera)."""
    from batocera_launch.config import defaults

    def _loader(system_name: str):
        if SWITCH_DEFAULTS.exists() and SWITCH_ARCH.exists():
            data = defaults.load_defaults(system_name, SWITCH_DEFAULTS, SWITCH_ARCH) or {}
            result = {'emulator': data.get('emulator'), 'core': data.get('core')}
            if 'options' in data:
                result.update(data['options'])
        else:
            result = original(system_name)
        emulator = emulator_name or result.get('emulator')
        result['hud_support'] = emulator != 'ryujinx-emu'
        return result

    return _loader


def run_native_api() -> None:
    """Batocera sans configgen : les générateurs sont enveloppés dans des classes Emulator."""
    import runpy
    from collections import ChainMap

    # Shim 'configgen' pour que les générateurs existants s'importent sans modification
    sys.path.insert(0, str(Path(__file__).resolve().parent / "compat"))

    from batocera_common.dataclasses import cached_dataclass, cached_property
    from batocera_launch.command import Command as LaunchCommand
    from batocera_launch.config import config as config_mod, defaults
    from batocera_launch.config.config import Config
    from batocera_launch.emulator import Emulator

    loader = _switch_load_system_defaults(defaults.load_system_defaults)
    defaults.load_system_defaults = loader
    config_mod.load_system_defaults = loader

    class _LegacySystem:
        """Imite l'objet `system` de l'ancien configgen."""

        def __init__(self, emu) -> None:
            self.name = emu.system
            self.config = Config(ChainMap(
                {'emulator': emu.name, 'core': emu.core or emu.name},
                emu.config.data,
            ))

        def isOptSet(self, key: str) -> bool:
            return key in self.config

        def getOptBoolean(self, key: str) -> bool:
            return self.config.get_bool(key)

        def getOptString(self, key: str) -> str:
            return self.config.get_str(key, '')

    def _make_class(factory):
        @cached_dataclass
        class SwitchEmulator(Emulator):
            @cached_property
            def generator(self):
                return factory()

            @cached_property
            def hotkeygen_context(self):
                return self.generator.getHotkeysContext()

            @property
            def execution_path(self):
                path = self.generator.executionDirectory(self.config, self.config.rom)
                return Path(path) if path else None

            @property
            def needs_mouse(self) -> bool:
                return bool(self.generator.getMouseMode(self.config, self.config.rom))

            @property
            def handles_bezels(self) -> bool:
                return True

            @cached_property
            def in_game_ratio(self) -> float:
                return 16 / 9

            async def configure(self) -> LaunchCommand:
                print(f'[SWITCH] emulator={self.name}', file=sys.stderr)
                print(f'[SWITCH] rom={os.path.basename(self.config.rom)}', file=sys.stderr)
                cmd = self.generator.generate(
                    _LegacySystem(self),
                    self.rom,
                    list(self.controllers),
                    self.metadata,
                    self.guns,
                    self.wheels,
                    {'width': self.resolution.width, 'height': self.resolution.height},
                )
                args = [a if isinstance(a, Path) else str(a) for a in cmd.array]
                env = {k: v if isinstance(v, Path) else str(v) for k, v in (cmd.env or {}).items()}
                return LaunchCommand(args=args, env=env)

        return SwitchEmulator

    def _eden():
        from generators.edenGenerator import EdenGenerator
        return EdenGenerator()

    def _ryujinx():
        from generators.ryujinxGenerator import RyujinxGenerator
        return RyujinxGenerator()

    eden_cls = _make_class(_eden)
    ryujinx_cls = _make_class(_ryujinx)
    original_load_class = Emulator._load_class

    def _load_class(name: str):
        if os.path.basename(rom) == 'ryujinx_config.xci_config':
            name = 'ryujinx-emu'
        if name in YUZU_LIKE:
            return eden_cls
        if name == 'ryujinx-emu':
            return ryujinx_cls
        return original_load_class(name)

    Emulator._load_class = staticmethod(_load_class)

    runpy.run_module('batocera_launch', run_name='__main__')


def run_old_api() -> None:
    """Batocera < 44."""
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
        if _has_real_configgen():
            run_new_api()      # v44 : configgen + batocera_launch coexistent
        else:
            run_native_api()   # configgen supprimé : batocera_launch seul
    else:
        run_old_api()
