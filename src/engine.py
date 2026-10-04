"""Key-event decisions, independent of any OS API.

The platform layer turns raw events into `on_key(name, down)` calls and replays
the returned key sequence. `None` always means "pass the original key through",
so any doubt (no rule, IME composing, Alt/Win held) leaves the app's own behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from src.keys import Combo
from src.rules import Rule

# Physical modifier keys, left/right kept apart so the exact key can be restored.
SIDE_MODIFIERS = {
    "lctrl": "ctrl", "rctrl": "ctrl",
    "lshift": "shift", "rshift": "shift",
    "lalt": "alt", "ralt": "alt",
    "lwin": "win", "rwin": "win",
}  # fmt: skip
# The side used when a combo needs a modifier that is not held.
PRESS_SIDE = {"ctrl": "lctrl", "shift": "lshift", "alt": "lalt"}

Output = tuple[str, bool]  # (key name, down)


@dataclass(frozen=True)
class Target:
    window_id: int
    rule: Rule | None


class Probe(Protocol):
    def target(self) -> Target: ...
    def ime_composes(self, window_id: int) -> bool: ...
    def is_down(self, name: str) -> bool: ...


class Engine:
    def __init__(self, probe: Probe, paused: Callable[[], bool] = lambda: False):
        self._probe = probe
        self._paused = paused
        self._held: set[str] = set()
        self._composing = 0  # characters typed into an IME composition, best effort
        self._window_id: int | None = None
        self._enter_swallowed = False

    @property
    def composing(self) -> int:
        return self._composing

    def cancel_enter(self) -> None:
        """The replacement could not be sent: let the Enter key-up through again."""
        self._enter_swallowed = False

    def on_key(self, name: str, down: bool) -> list[Output] | None:
        if name in SIDE_MODIFIERS:
            (self._held.add if down else self._held.discard)(name)
            return None
        if name == "enter":
            return self._on_enter(down)
        if down:
            self._track_composition(name)
        return None

    def _generic_held(self) -> set[str]:
        return {SIDE_MODIFIERS[k] for k in self._held}

    def _on_enter(self, down: bool) -> list[Output] | None:
        if not down:
            swallowed, self._enter_swallowed = self._enter_swallowed, False
            return [] if swallowed else None
        rule = self._active_rule()
        # Key-ups missed while the hook was blind (secure desktop, startup) would
        # otherwise be "restored" as stuck modifiers, so trust only keys still down.
        self._held = {k for k in self._held if self._probe.is_down(k)}
        held = self._generic_held()
        if rule is None or self._paused() or held & {"alt", "win"}:
            self._enter_swallowed = False
            return None
        if self._composing:
            # The IME takes this Enter to confirm the conversion.
            self._composing = 0
            self._enter_swallowed = False
            return None
        combo = rule.submit if "ctrl" in held else rule.newline
        self._enter_swallowed = True
        return self._sequence(combo)

    def _sequence(self, combo: Combo) -> list[Output]:
        release = sorted(
            k for k in self._held if SIDE_MODIFIERS[k] not in combo.modifiers
        )
        generic = self._generic_held()
        press = sorted(PRESS_SIDE[m] for m in combo.modifiers if m not in generic)
        return [
            *[(k, False) for k in release],
            *[(k, True) for k in press],
            (combo.key, True),
            (combo.key, False),
            *[(k, False) for k in reversed(press)],
            *[(k, True) for k in release],
        ]

    def _active_rule(self) -> Rule | None:
        target = self._probe.target()
        if target.window_id != self._window_id:
            self._window_id = target.window_id
            self._composing = 0
        return target.rule

    def _track_composition(self, name: str) -> None:
        if name in ("escape", "nav"):
            self._composing = 0
        elif name == "backspace":
            self._composing = max(0, self._composing - 1)
        elif name == "char" and not self._generic_held() & {"ctrl", "alt", "win"}:
            rule = self._active_rule()
            if (
                rule is not None
                and self._window_id is not None
                and self._probe.ime_composes(self._window_id)
            ):
                self._composing += 1
