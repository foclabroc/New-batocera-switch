from __future__ import annotations

from typing import Any


class Generator:
    """Base minimale compatible avec l'ancien configgen.generators.Generator."""

    def generate(self, system: Any, rom: Any, playersControllers: Any, metadata: Any,
                 guns: Any, wheels: Any, gameResolution: Any) -> Any:
        raise NotImplementedError

    def getHotkeysContext(self) -> Any:
        raise NotImplementedError

    def executionDirectory(self, config: Any, rom: Any) -> str | None:
        return None

    def getMouseMode(self, config: Any, rom: Any) -> bool:
        return False

    def getInGameRatio(self, config: Any, gameResolution: Any, rom: Any) -> float:
        return 16 / 9
