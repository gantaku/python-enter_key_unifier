import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows backend")


class FakeEngine:
    def __init__(self):
        self.cancelled = 0

    def cancel_enter(self):
        self.cancelled += 1


SEQUENCE = [("lshift", False), ("lctrl", True), ("j", True), ("j", False), ("lctrl", False), ("lshift", True)]


def make_hook(monkeypatch, results):
    from src import platform_win

    calls = []

    def fake_send(sequence):
        calls.append(list(sequence))
        return results.pop(0)

    monkeypatch.setattr(platform_win, "send_keys", fake_send)
    engine = FakeEngine()
    return platform_win.KeyboardHook(engine), engine, calls


def test_send_failure_passes_original_key(monkeypatch):
    hook, engine, _ = make_hook(monkeypatch, [0])
    assert hook._send(SEQUENCE) is False
    assert engine.cancelled == 1


def test_partial_send_restores_remaining_modifiers(monkeypatch):
    hook, _, calls = make_hook(monkeypatch, [3, 2])
    assert hook._send(SEQUENCE) is True
    assert calls[1] == [("lctrl", False), ("lshift", True)]


def test_full_send(monkeypatch):
    hook, engine, calls = make_hook(monkeypatch, [len(SEQUENCE)])
    assert hook._send(SEQUENCE) is True
    assert len(calls) == 1 and engine.cancelled == 0


def test_key_names():
    from src.platform_win import key_name

    assert key_name(0x0D) == "enter"
    assert key_name(0x41) == "char"
    assert key_name(0x25) == "nav"
    assert key_name(0x09) == "nav"
    assert key_name(0xA3) == "rctrl"
    assert key_name(0x70) == "other"
