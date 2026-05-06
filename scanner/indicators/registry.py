from dataclasses import dataclass, field
from typing import Type
from .base import BaseIndicator


@dataclass
class IndicatorEntry:
    cls: Type[BaseIndicator]
    group: str
    params: dict = field(default_factory=dict)
    enabled: bool = True


INDICATORS: list[IndicatorEntry] = []


def register(group: str, params: dict = None):
    """Decorator that registers an indicator class in the INDICATORS list."""
    def decorator(cls: Type[BaseIndicator]) -> Type[BaseIndicator]:
        INDICATORS.append(IndicatorEntry(cls=cls, group=group, params=params or {}))
        return cls
    return decorator


def get_enabled_indicators(toggles: dict = None) -> list[IndicatorEntry]:
    """Return all enabled indicator entries, respecting user toggles from Settings."""
    toggles = toggles or {}
    return [
        entry for entry in INDICATORS
        if toggles.get(entry.cls.__name__, entry.enabled)
    ]
