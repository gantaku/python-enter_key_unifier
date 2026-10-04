"""OS-neutral key names and key combos ("ctrl+j", "shift+enter", "enter")."""

from __future__ import annotations

from dataclasses import dataclass

MODIFIERS = ("ctrl", "shift", "alt")
KEYS = ("enter", "j")


@dataclass(frozen=True)
class Combo:
    modifiers: frozenset[str]
    key: str

    def __str__(self) -> str:
        return "+".join([*sorted(self.modifiers), self.key])


def parse_combo(text: str) -> Combo:
    """Parse "ctrl+j" style text. Raises ValueError on anything outside the small allowed set."""
    parts = [p.strip().lower() for p in text.split("+")]
    if not parts or any(not p for p in parts):
        raise ValueError(f"invalid key combo: {text!r}")
    *mods, key = parts
    if key not in KEYS:
        raise ValueError(
            f"unsupported key {key!r} in {text!r} (allowed: {', '.join(KEYS)})"
        )
    unknown = [m for m in mods if m not in MODIFIERS]
    if unknown or len(set(mods)) != len(mods):
        raise ValueError(f"invalid modifiers in {text!r}")
    return Combo(frozenset(mods), key)
