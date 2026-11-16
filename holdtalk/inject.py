# -*- coding: utf-8 -*-
"""把识别结果送进当前光标位置。

两种方式：
- clipboard：备份剪贴板 → 写入 → Ctrl+V → 还原。快，兼容绝大多数应用。
- typing：SendInput 逐字符发送 Unicode。不碰剪贴板，但慢一些，
  个别应用（部分游戏、远程桌面）会更稳。
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_CONTROL = 0x11
VK_V = 0x56
VK_SHIFT = 0x10
VK_INSERT = 0x2D

# ---- 64 位安全的原型声明 ----
user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.restype = wintypes.BOOL
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.restype = wintypes.BOOL


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("padding", ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


def _send_key(vk: int, up: bool = False, unicode_char: str | None = None) -> None:
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.u.ki.wVk = 0 if unicode_char else vk
    inp.u.ki.wScan = ord(unicode_char) if unicode_char else 0
    flags = 0
    if unicode_char:
        flags |= KEYEVENTF_UNICODE
    if up:
        flags |= KEYEVENTF_KEYUP
    inp.u.ki.dwFlags = flags
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


# ---------------- 剪贴板 ----------------
def _open_clipboard(retries: int = 12, delay: float = 0.02) -> bool:
    for _ in range(retries):
        if user32.OpenClipboard(None):
            return True
        time.sleep(delay)
    return False


def get_clipboard_text() -> str | None:
    if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
        return None
    if not _open_clipboard():
        return None
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return None
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def set_clipboard_text(text: str) -> bool:
    if not _open_clipboard():
        return False
    try:
        user32.EmptyClipboard()
        buf = ctypes.create_unicode_buffer(text)
        size = ctypes.sizeof(buf)
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
        if not handle:
            return False
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return False
        try:
            ctypes.memmove(ptr, buf, size)
        finally:
            kernel32.GlobalUnlock(handle)
        return bool(user32.SetClipboardData(CF_UNICODETEXT, handle))
    finally:
        user32.CloseClipboard()


def _paste(vim_mode: bool = False) -> None:
    time.sleep(0.02)
    if vim_mode:
        # 终端里 Ctrl+V 不是粘贴，Ctrl+Shift+V 才是
        user32.keybd_event(VK_CONTROL, 0, 0, 0)
        user32.keybd_event(VK_SHIFT, 0, 0, 0)
        user32.keybd_event(VK_V, 0, 0, 0)
        time.sleep(0.02)
        user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_SHIFT, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
    else:
        user32.keybd_event(VK_CONTROL, 0, 0, 0)
        time.sleep(0.01)
        user32.keybd_event(VK_V, 0, 0, 0)
        time.sleep(0.02)
        user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


# ---------------- 对外接口 ----------------
def paste_text(text: str, method: str = "clipboard",
               vim_mode: bool = False, restore_clipboard: bool = True,
               settle: float = 0.12) -> bool:
    """把文本送进当前焦点控件。返回是否成功。"""
    if not text:
        return False
    if method == "typing":
        return type_text(text)

    backup = get_clipboard_text() if restore_clipboard else None
    if not set_clipboard_text(text):
        return type_text(text)  # 剪贴板写不进去时兜底

    time.sleep(0.05)
    _paste(vim_mode=vim_mode)
    time.sleep(settle)  # 等目标应用把内容取走

    if restore_clipboard and backup is not None:
        set_clipboard_text(backup)
    return True


def type_text(text: str, per_char_delay: float = 0.002) -> bool:
    """逐字符 Unicode 注入，不经过剪贴板。"""
    for ch in text:
        if ch == "\n":
            _send_key(0x0D)
            _send_key(0x0D, up=True)
        else:
            _send_key(0, unicode_char=ch)
            _send_key(0, up=True, unicode_char=ch)
        if per_char_delay:
            time.sleep(per_char_delay)
    return True


def beep(freq: int = 880, duration_ms: int = 60) -> None:
    """轻提示音：开始/结束各响一下，不依赖任何音频库。"""
    try:
        ctypes.windll.kernel32.Beep(freq, duration_ms)
    except Exception:
        pass
