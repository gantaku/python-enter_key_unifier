"""Windows backend: low-level keyboard hook, SendInput, foreground window and IME state.

Fail-open by design: any exception inside the hook passes the original key on, and
Windows itself removes a hook that stops answering, which also restores normal keys.
"""

from __future__ import annotations

import ctypes
import logging
import threading
from ctypes import wintypes
from typing import Callable

from src.engine import Engine, Target
from src.rules import Rule, WindowInfo, find_rule

log = logging.getLogger(__name__)

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
imm32 = ctypes.WinDLL("imm32", use_last_error=True)

WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x104, 0x105
WM_QUIT = 0x12
WM_IME_CONTROL = 0x283
IMC_GETCONVERSIONMODE, IMC_GETOPENSTATUS = 0x1, 0x5
IME_CMODE_NATIVE = 0x1
SMTO_ABORTIFHUNG = 0x2
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP = 0x1, 0x2
# Marks our own SendInput events so the hook lets them through untouched.
INJECTED_MARK = 0x454B5531  # "EKU1"

VK_BY_NAME = {
    "enter": 0x0D, "j": 0x4A,
    "lctrl": 0xA2, "rctrl": 0xA3, "lshift": 0xA0, "rshift": 0xA1,
    "lalt": 0xA4, "ralt": 0xA5, "lwin": 0x5B, "rwin": 0x5C,
    "backspace": 0x08, "escape": 0x1B,
}  # fmt: skip
# Tab, Page Up/Down, End, Home and arrows move the caret: treated as ending a composition.
NAV_VKS = frozenset([0x09, *range(0x21, 0x29)])
NAME_BY_VK = {vk: name for name, vk in VK_BY_NAME.items() if name != "j"}
EXTENDED = {"rctrl", "ralt", "lwin", "rwin"}
# Keys that start or extend an IME composition: letters, digits, OEM punctuation, numpad.
CHAR_VKS = frozenset(
    [*range(0x30, 0x3A), *range(0x41, 0x5B), *range(0x60, 0x70),
     *range(0xBA, 0xC1), *range(0xDB, 0xE0), 0xE2]
)  # fmt: skip

ULONG_PTR = ctypes.c_size_t
LRESULT = ctypes.c_ssize_t


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

user32.SetWindowsHookExW.argtypes = [
    ctypes.c_int,
    HOOKPROC,
    wintypes.HINSTANCE,
    wintypes.DWORD,
]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [
    wintypes.HHOOK,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.GetMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
]
user32.PostThreadMessageW.argtypes = [
    wintypes.DWORD,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [
    wintypes.HWND,
    ctypes.POINTER(wintypes.DWORD),
]
user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
user32.SendMessageTimeoutW.argtypes = [
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    wintypes.UINT, wintypes.UINT, ctypes.POINTER(ULONG_PTR),
]  # fmt: skip
user32.SendMessageTimeoutW.restype = LRESULT
imm32.ImmGetDefaultIMEWnd.argtypes = [wintypes.HWND]
imm32.ImmGetDefaultIMEWnd.restype = wintypes.HWND
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD),
]  # fmt: skip
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.GetCurrentThreadId.restype = wintypes.DWORD


def window_info(hwnd) -> WindowInfo | None:
    if not hwnd:
        return None
    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return WindowInfo(process=_process_name(pid.value), title=buffer.value)


_process_cache: dict[int, str] = {}


def _process_name(pid: int) -> str:
    if pid in _process_cache:
        return _process_cache[pid]
    name = ""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if handle:
        try:
            size = wintypes.DWORD(1024)
            buffer = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(
                handle, 0, buffer, ctypes.byref(size)
            ):
                name = buffer.value.rsplit("\\", 1)[-1].lower()
        finally:
            kernel32.CloseHandle(handle)
    if len(_process_cache) > 256:
        _process_cache.clear()
    _process_cache[pid] = name
    return name


def _ime_control(ime_hwnd, command: int) -> int | None:
    result = ULONG_PTR()
    ok = user32.SendMessageTimeoutW(
        ime_hwnd,
        WM_IME_CONTROL,
        command,
        0,
        SMTO_ABORTIFHUNG,
        30,
        ctypes.byref(result),
    )
    return result.value if ok else None


class WindowsProbe:
    """Answers the engine's questions about the foreground window."""

    def __init__(self, rules: Callable[[], tuple[Rule, ...]]):
        self._rules = rules
        self._last_match: tuple[int, str | None] | None = None

    def target(self) -> Target:
        hwnd = user32.GetForegroundWindow() or 0
        rule = find_rule(self._rules(), window_info(hwnd))
        key = (hwnd, rule.name if rule else None)
        if key != self._last_match:
            self._last_match = key
            log.info("foreground %s: rule=%s", hwnd, key[1])
        return Target(hwnd, rule)

    def ime_composes(self, window_id: int) -> bool:
        ime_hwnd = imm32.ImmGetDefaultIMEWnd(window_id)
        if not ime_hwnd:
            return False
        if not _ime_control(ime_hwnd, IMC_GETOPENSTATUS):
            return False
        mode = _ime_control(ime_hwnd, IMC_GETCONVERSIONMODE)
        return bool(mode is not None and mode & IME_CMODE_NATIVE)

    def is_down(self, name: str) -> bool:
        return bool(user32.GetAsyncKeyState(VK_BY_NAME[name]) & 0x8000)


def send_keys(sequence: list[tuple[str, bool]]) -> int:
    """Inject the sequence; returns how many events Windows accepted."""
    inputs = (INPUT * len(sequence))()
    for item, (name, down) in zip(inputs, sequence):
        vk = VK_BY_NAME[name]
        flags = (0 if down else KEYEVENTF_KEYUP) | (
            KEYEVENTF_EXTENDEDKEY if name in EXTENDED else 0
        )
        item.type = INPUT_KEYBOARD
        item.u.ki = KEYBDINPUT(
            vk, user32.MapVirtualKeyW(vk, 0), flags, 0, INJECTED_MARK
        )
    sent = user32.SendInput(len(sequence), inputs, ctypes.sizeof(INPUT))
    if sent != len(sequence):
        log.warning(
            "SendInput sent %d of %d events (error %d)",
            sent,
            len(sequence),
            ctypes.get_last_error(),
        )
    return sent


def key_name(vk: int) -> str:
    if vk in NAME_BY_VK:
        return NAME_BY_VK[vk]
    if vk in NAV_VKS:
        return "nav"
    return "char" if vk in CHAR_VKS else "other"


class KeyboardHook:
    """Runs the low-level hook on its own thread with a message loop."""

    def __init__(self, engine: Engine):
        self._engine = engine
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._ready = threading.Event()
        self._proc = HOOKPROC(
            self._callback
        )  # keep a reference for the hook's lifetime

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, name="keyboard-hook", daemon=True
        )
        self._thread.start()
        self._ready.wait(5)

    def stop(self) -> None:
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread:
            self._thread.join(5)

    def _send(self, sequence: list[tuple[str, bool]]) -> bool:
        """True when the replacement went out. On failure the original key passes through."""
        sent = send_keys(sequence)
        if sent == len(sequence):
            return True
        if sent == 0:
            self._engine.cancel_enter()
            return False
        # Partly sent: finish the modifier restores so nothing stays stuck or released.
        modifiers = [(n, d) for n, d in sequence[sent:] if n not in ("enter", "j")]
        if modifiers:
            send_keys(modifiers)
        return True

    def _run(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, None, 0)
        self._ready.set()
        if not hook:
            log.error("SetWindowsHookEx failed (error %d)", ctypes.get_last_error())
            return
        log.info("keyboard hook installed")
        try:
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                pass
        finally:
            user32.UnhookWindowsHookEx(hook)
            log.info("keyboard hook removed")

    def _callback(self, code: int, wparam: int, lparam: int) -> int:
        try:
            if code == 0 and wparam in (
                WM_KEYDOWN,
                WM_KEYUP,
                WM_SYSKEYDOWN,
                WM_SYSKEYUP,
            ):
                event = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if event.dwExtraInfo != INJECTED_MARK:
                    down = wparam in (WM_KEYDOWN, WM_SYSKEYDOWN)
                    sequence = self._engine.on_key(key_name(event.vkCode), down)
                    if sequence is not None:
                        if not sequence or self._send(sequence):
                            return 1
        except Exception:  # noqa: BLE001 - never block the keyboard on a bug
            self._engine.cancel_enter()
            log.exception("hook error; key passed through")
        return user32.CallNextHookEx(None, code, wparam, lparam)
