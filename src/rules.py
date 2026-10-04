"""Which window gets which keys. OS-neutral: the platform layer fills in WindowInfo."""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.keys import Combo


@dataclass(frozen=True)
class WindowInfo:
    process: str  # executable name, lower case ("windowsterminal.exe")
    title: str


@dataclass(frozen=True)
class Rule:
    name: str
    process: str
    title_pattern: re.Pattern[str] | None
    newline: Combo
    submit: Combo

    def matches(self, window: WindowInfo) -> bool:
        if window.process != self.process:
            return False
        return (
            self.title_pattern is None
            or self.title_pattern.search(window.title) is not None
        )


def find_rule(rules: tuple[Rule, ...], window: WindowInfo | None) -> Rule | None:
    """First matching rule, or None. No match means the key passes through untouched."""
    if window is None:
        return None
    return next((rule for rule in rules if rule.matches(window)), None)
