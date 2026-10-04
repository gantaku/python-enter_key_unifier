import re

import pytest

from src.engine import Engine, Target
from src.keys import parse_combo
from src.rules import Rule

CLAUDE = Rule(
    name="claude",
    process="windowsterminal.exe",
    title_pattern=re.compile("^✳ "),
    newline=parse_combo("ctrl+j"),
    submit=parse_combo("enter"),
)


class FakeProbe:
    def __init__(self, rule=CLAUDE, window_id=1, ime=False):
        self.rule = rule
        self.window_id = window_id
        self.ime = ime
        self.released = set()  # modifiers whose key-up the hook never saw

    def target(self):
        return Target(self.window_id, self.rule)

    def ime_composes(self, window_id):
        return self.ime

    def is_down(self, name):
        return name not in self.released


def press(engine, *names):
    out = None
    for name in names:
        out = engine.on_key(name, True)
    return out


def test_enter_becomes_ctrl_j():
    engine = Engine(FakeProbe())
    assert engine.on_key("enter", True) == [
        ("lctrl", True), ("j", True), ("j", False), ("lctrl", False),
    ]  # fmt: skip
    assert engine.on_key("enter", False) == []


def test_shift_enter_releases_shift_then_restores_it():
    engine = Engine(FakeProbe())
    engine.on_key("lshift", True)
    assert engine.on_key("enter", True) == [
        ("lshift", False), ("lctrl", True), ("j", True), ("j", False),
        ("lctrl", False), ("lshift", True),
    ]  # fmt: skip


def test_ctrl_enter_becomes_plain_enter_with_ctrl_restored():
    engine = Engine(FakeProbe())
    engine.on_key("rctrl", True)
    assert engine.on_key("enter", True) == [
        ("rctrl", False), ("enter", True), ("enter", False), ("rctrl", True),
    ]  # fmt: skip


def test_no_rule_passes_through():
    engine = Engine(FakeProbe(rule=None))
    assert engine.on_key("enter", True) is None
    assert engine.on_key("enter", False) is None


def test_paused_passes_through():
    engine = Engine(FakeProbe(), paused=lambda: True)
    assert engine.on_key("enter", True) is None


@pytest.mark.parametrize("modifier", ["lalt", "ralt", "lwin"])
def test_alt_or_win_enter_passes_through(modifier):
    engine = Engine(FakeProbe())
    engine.on_key(modifier, True)
    assert engine.on_key("enter", True) is None


def test_ime_composition_enter_passes_through_once():
    engine = Engine(FakeProbe(ime=True))
    press(engine, "char", "char")
    assert engine.composing == 2
    assert engine.on_key("enter", True) is None  # confirms the conversion
    assert engine.on_key("enter", False) is None
    assert engine.on_key("enter", True) is not None  # next Enter is a newline


def test_backspace_and_escape_end_composition():
    engine = Engine(FakeProbe(ime=True))
    press(engine, "char", "backspace")
    assert engine.composing == 0
    press(engine, "char", "char", "escape")
    assert engine.composing == 0


def test_ime_off_typing_does_not_compose():
    engine = Engine(FakeProbe(ime=False))
    press(engine, "char", "char")
    assert engine.on_key("enter", True) is not None


def test_ctrl_shortcuts_do_not_compose():
    engine = Engine(FakeProbe(ime=True))
    engine.on_key("lctrl", True)
    press(engine, "char")
    assert engine.composing == 0


def test_window_change_resets_composition():
    probe = FakeProbe(ime=True)
    engine = Engine(probe)
    press(engine, "char")
    probe.window_id = 2
    assert engine.on_key("enter", True) is not None


def test_modifier_release_is_tracked():
    engine = Engine(FakeProbe())
    engine.on_key("lctrl", True)
    engine.on_key("lctrl", False)
    assert engine.on_key("enter", True)[1] == ("j", True)


def test_unswallowed_enter_up_passes_after_swallowed_down():
    probe = FakeProbe()
    engine = Engine(probe)
    engine.on_key("enter", True)
    assert engine.on_key("enter", False) == []
    probe.rule = None
    engine.on_key("enter", True)
    assert engine.on_key("enter", False) is None


def test_stale_modifier_is_not_restored():
    probe = FakeProbe()
    engine = Engine(probe)
    engine.on_key("lshift", True)
    probe.released.add("lshift")  # key-up lost (e.g. secure desktop)
    assert engine.on_key("enter", True) == [
        ("lctrl", True), ("j", True), ("j", False), ("lctrl", False),
    ]  # fmt: skip


def test_stale_ctrl_does_not_turn_enter_into_submit():
    probe = FakeProbe()
    engine = Engine(probe)
    engine.on_key("lctrl", True)
    probe.released.add("lctrl")
    assert ("j", True) in engine.on_key("enter", True)


def test_cancel_enter_lets_key_up_through():
    engine = Engine(FakeProbe())
    engine.on_key("enter", True)
    engine.cancel_enter()
    assert engine.on_key("enter", False) is None


def test_caret_keys_end_composition():
    engine = Engine(FakeProbe(ime=True))
    press(engine, "char", "nav")
    assert engine.composing == 0
