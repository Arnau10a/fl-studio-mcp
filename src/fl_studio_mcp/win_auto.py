"""Windows GUI automation and sample-library search helpers for FL Studio."""

from __future__ import annotations

import contextlib
import ctypes
import ctypes.wintypes as wintypes
import os
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fl_studio_mcp.paths import get_output_dir

_windll: Any = getattr(ctypes, "WinDLL", None)
user32: Any = (
    _windll("user32", use_last_error=True) if (sys.platform == "win32" and _windll) else None
)


def _require_user32() -> Any:
    if user32 is None:
        raise RuntimeError("Windows GUI automation is only supported on Windows.")
    return user32


INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
SW_RESTORE = 9

VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt
VK_ESCAPE = 0x1B
VK_DELETE = 0x2E
VK_DOWN = 0x28
VK_F7 = 0x76
VK_F8 = 0x77
VK_F10 = 0x79
VK_APPS = 0x5D

AUDIO_EXTS = {".wav", ".wv", ".ogg", ".mp3", ".flac", ".aif", ".aiff"}
DEFAULT_PACKS_DIRS = [
    Path(r"C:\Program Files\Image-Line\FL Studio 2024\Data\Patches\Packs"),
    Path(r"C:\Program Files\Image-Line\FL Studio 21\Data\Patches\Packs"),
    Path.home() / "Documents" / "Image-Line" / "FL Studio" / "Audio",
]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("ki", KEYBDINPUT),
        ("mi", MOUSEINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", _INPUT_UNION),
    ]


def _send_vk(vk: int, key_up: bool = False) -> None:
    u32 = _require_user32()
    flags = KEYEVENTF_KEYUP if key_up else 0
    inp = INPUT(
        type=INPUT_KEYBOARD,
        union=_INPUT_UNION(ki=KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=None)),
    )
    u32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def tap_vk(vk: int, hold_s: float = 0.02) -> None:
    _send_vk(vk, False)
    time.sleep(hold_s)
    _send_vk(vk, True)


def hotkey(*vks: int) -> None:
    for vk in vks:
        _send_vk(vk, False)
        time.sleep(0.015)
    time.sleep(0.03)
    for vk in reversed(vks):
        _send_vk(vk, True)
        time.sleep(0.015)


def type_text(text: str, delay_s: float = 0.012) -> None:
    u32 = _require_user32()
    for ch in text:
        code = ord(ch)
        down = INPUT(
            type=INPUT_KEYBOARD,
            union=_INPUT_UNION(
                ki=KEYBDINPUT(
                    wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=None
                )
            ),
        )
        up = INPUT(
            type=INPUT_KEYBOARD,
            union=_INPUT_UNION(
                ki=KEYBDINPUT(
                    wVk=0,
                    wScan=code,
                    dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
                    time=0,
                    dwExtraInfo=None,
                )
            ),
        )
        u32.SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT))
        u32.SendInput(1, ctypes.byref(up), ctypes.sizeof(INPUT))
        time.sleep(delay_s)


def find_fl_studio_hwnd() -> int | None:
    u32 = _require_user32()
    matches: list[int] = []
    winfunct: Any = getattr(ctypes, "WINFUNCTYPE", None)
    enum_windows_proc = winfunct(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _cb(hwnd: int, _lparam: int) -> bool:
        if not u32.IsWindowVisible(hwnd):
            return True
        length = u32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        u32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        if "FL Studio" in title:
            matches.append(hwnd)
        return True

    u32.EnumWindows(enum_windows_proc(_cb), 0)
    return matches[0] if matches else None


def focus_fl_studio() -> int:
    u32 = _require_user32()
    hwnd = find_fl_studio_hwnd()
    if hwnd is None:
        raise RuntimeError("FL Studio window not found.")
    if u32.IsIconic(hwnd):
        u32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.1)
    # Tapping Alt bypasses Windows' foreground lock restriction
    _send_vk(VK_MENU, False)
    u32.SetForegroundWindow(hwnd)
    _send_vk(VK_MENU, True)
    time.sleep(0.15)
    return hwnd


@contextlib.contextmanager
def preserve_foreground() -> Iterator[int]:
    """Focus FL Studio for a GUI action and restore the previous foreground window afterward."""
    u32 = _require_user32()
    prev_hwnd = int(u32.GetForegroundWindow() or 0)
    fl_hwnd = focus_fl_studio()
    try:
        yield fl_hwnd
    finally:
        if prev_hwnd and prev_hwnd != fl_hwnd and u32.IsWindow(prev_hwnd):
            _send_vk(VK_MENU, False)
            u32.SetForegroundWindow(prev_hwnd)
            _send_vk(VK_MENU, True)


def get_foreground_info() -> tuple[int, str, str]:
    u32 = _require_user32()
    hwnd = u32.GetForegroundWindow()
    if not hwnd:
        return (0, "", "")
    t_len = u32.GetWindowTextLengthW(hwnd)
    t_buf = ctypes.create_unicode_buffer(t_len + 1)
    u32.GetWindowTextW(hwnd, t_buf, t_len + 1)
    c_buf = ctypes.create_unicode_buffer(256)
    u32.GetClassNameW(hwnd, c_buf, 256)
    return (hwnd, t_buf.value, c_buf.value)


def search_samples(
    query: str, category: str | None = None, limit: int = 25
) -> list[dict[str, str]]:
    """Search FL Studio's Packs directories (and local output/) for audio samples."""
    terms = [t.lower() for t in query.split() if t.strip()]
    roots = [p for p in DEFAULT_PACKS_DIRS if p.exists()]
    local_out = get_output_dir()
    if local_out.exists():
        roots.append(local_out)

    results: list[dict[str, str]] = []
    for root in roots:
        search_root = root / category if (category and (root / category).exists()) else root
        for dirpath, _dirnames, filenames in os.walk(search_root):
            for fname in filenames:
                ext = Path(fname).suffix.lower()
                if ext not in AUDIO_EXTS:
                    continue
                full_path = os.path.join(dirpath, fname)
                hay = full_path.lower()
                if all(t in hay for t in terms):
                    results.append(
                        {
                            "name": Path(fname).stem,
                            "filename": fname,
                            "path": full_path,
                        }
                    )
                    if len(results) >= limit:
                        return results
    return results
