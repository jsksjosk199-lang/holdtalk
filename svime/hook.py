# -*- coding: utf-8 -*-
"""低级鼠标钩子：长按中键触发录音，短按原样透传。

和旧版的关键差异：
1. 短按不再在钩子回调里 sleep（旧版 sleep 50ms 会卡住整条鼠标事件链）；
2. 长按判定由独立 Timer 完成，钩子回调只记账，永远快速返回；
3. 增加全局单实例锁，避免多开后一条录音被处理两遍。
"""

from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes
from typing import Callable, Optional

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)

WH_MOUSE_LL = 14
HC_ACTION = 0
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
ERROR_ALREADY_EXISTS = 183

LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", wintypes.POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p, wintypes.HMODULE, wintypes.DWORD]
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.CallNextHookEx.restype = LRESULT
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.mouse_event.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]


def acquire_single_instance(name: str = "Global\\SenseVoiceIME") -> Optional[int]:
    """拿全局互斥量。返回句柄表示拿到；返回 None 表示已有实例在跑。"""
    handle = kernel32.CreateMutexW(None, False, name)
    if not handle:
        return None
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:  # type: ignore[attr-defined]
        kernel32.CloseHandle(handle)
        return None
    return handle


class MiddleHoldHook:
    """监听鼠标中键。长按超过 threshold_ms 判定为一次语音输入。

    回调约定：
      on_hold_start()  长按成立，开始录音
      on_hold_end()    松开，结束录音（异步处理）
    """

    def __init__(
        self,
        threshold_ms: int = 350,
        on_hold_start: Optional[Callable[[], None]] = None,
        on_hold_end: Optional[Callable[[], None]] = None,
        restore_middle_click: bool = True,
        logger=None,
    ) -> None:
        self.threshold = max(80, int(threshold_ms)) / 1000.0
        self.on_hold_start = on_hold_start or (lambda: None)
        self.on_hold_end = on_hold_end or (lambda: None)
        self.restore_middle_click = bool(restore_middle_click)
        self._log = logger or (lambda *a, **k: None)

        self._pressed_at = 0.0
        self._holding = False
        self._timer: Optional[threading.Timer] = None
        self._hook = None
        self._proc_ref = None
        self._lock = threading.Lock()
        self._stopped = False
        self._thread_id = 0

    # ---------------- 内部 ----------------
    def _arm(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self.threshold, self._on_threshold)
            self._timer.daemon = True
            self._timer.start()

    def _disarm(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

    def _on_threshold(self) -> None:
        """长按阈值到达：确认仍然按着，才开始录音。"""
        with self._lock:
            self._timer = None
            if self._stopped or self._pressed_at <= 0 or self._holding:
                return
            self._holding = True
        try:
            self.on_hold_start()
        except Exception as exc:  # 回调异常绝不能把钩子带崩
            self._log(f"[hook] on_hold_start 异常: {exc}")

    def _emit_middle_click(self) -> None:
        """短按透传：发一次完整中键点击。不 sleep，不阻塞钩子。"""
        user32.mouse_event(MOUSEEVENTF_MIDDLEDOWN, 0, 0, 0, 0)
        user32.mouse_event(MOUSEEVENTF_MIDDLEUP, 0, 0, 0, 0)

    def _handle(self, wparam: int) -> None:
        if wparam == WM_MBUTTONDOWN:
            with self._lock:
                if self._holding:  # 已在录音中，忽略重复按下
                    return
                self._pressed_at = time.monotonic()
            self._arm()
        elif wparam == WM_MBUTTONUP:
            self._disarm()
            with self._lock:
                was_holding = self._holding
                self._holding = False
                self._pressed_at = 0.0
            if was_holding:
                try:
                    self.on_hold_end()
                except Exception as exc:
                    self._log(f"[hook] on_hold_end 异常: {exc}")
            elif self.restore_middle_click:
                self._emit_middle_click()

    # ---------------- 安装 ----------------
    def _proc(self, n_code, w_param, l_param):  # noqa: ANN001
        if n_code == HC_ACTION and not self._stopped:
            try:
                # 只在钩子线程里做最少的事，保证 300ms 超时线内返回
                if w_param in (WM_MBUTTONDOWN, WM_MBUTTONUP):
                    self._handle(w_param)
                    return 1  # 抑制原始事件，由我们决定透传时机
            except Exception as exc:
                self._log(f"[hook] 处理异常: {exc}")
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    def run(self) -> None:
        """阻塞运行消息循环（必须在主线程调用）。"""
        self._proc_ref = HOOKPROC(self._proc)
        self._thread_id = kernel32.GetCurrentThreadId()
        h_mod = kernel32.GetModuleHandleW(None)
        self._hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._proc_ref, h_mod, 0)
        if not self._hook:
            err = ctypes.get_last_error()
            hint = {5: "权限不足，请以管理员身份运行", 1428: "需要有效模块句柄"}.get(err, "")
            raise RuntimeError(f"安装鼠标钩子失败（GetLastError={err}）{hint}")

        self._log("[hook] 鼠标中键钩子已安装")
        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            self.stop()

    def stop(self) -> None:
        self._stopped = True
        self._disarm()
        if self._hook:
            user32.UnhookWindowsHookEx(self._hook)
            self._hook = None
            self._log("[hook] 钩子已卸载")

    def stop_async(self) -> None:
        """从别的线程安全地结束消息循环。"""
        self._stopped = True
        self._disarm()
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)  # WM_QUIT
