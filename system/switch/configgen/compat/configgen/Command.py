from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Command:
    array: list[Any]
    env: dict[str, Any] = field(default_factory=dict)
