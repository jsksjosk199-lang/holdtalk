# -*- coding: utf-8 -*-
"""麦克风录音：按下开始、松开停止，回放后交给 ASR。"""

from __future__ import annotations

import threading
import time
from typing import Optional

import numpy as np

SAMPLE_RATE = 16000


class Recorder:
    """基于 sounddevice 的极简录音器，按需开流，避免常驻占用麦克风。"""

    def __init__(self, sample_rate: int = SAMPLE_RATE, device=None) -> None:
        self.sample_rate = int(sample_rate)
        self.device = device
        self._stream = None
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._recording = False
        self._started_at = 0.0

    # ---------------- 状态 ----------------
    @property
    def recording(self) -> bool:
        return self._recording

    @property
    def duration(self) -> float:
        return time.time() - self._started_at if self._recording else 0.0

    # ---------------- 启动 / 停止 ----------------
    def start(self) -> bool:
        if self._recording:
            return True
        try:
            import sounddevice as sd
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("缺少 sounddevice，请先执行：pip install sounddevice") from exc

        with self._lock:
            self._chunks = []

        def _cb(indata, frames, time_info, status):  # noqa: ARG001
            if self._recording:
                with self._lock:
                    self._chunks.append(indata.copy().reshape(-1))

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                blocksize=int(self.sample_rate * 0.05),
                device=self.device,
                callback=_cb,
            )
            self._stream.start()
        except Exception:
            self._close()
            raise

        self._recording = True
        self._started_at = time.time()
        return True

    def stop(self) -> np.ndarray:
        """停止录音并返回 float32 单声道采样。"""
        if not self._recording:
            return np.zeros(0, dtype=np.float32)
        self._recording = False
        self._close()
        with self._lock:
            chunks = self._chunks
            self._chunks = []
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        audio = np.concatenate(chunks).astype(np.float32)
        return audio

    def cancel(self) -> None:
        """放弃本次录音（例如超时或用户取消）。"""
        self._recording = False
        self._close()
        with self._lock:
            self._chunks = []

    def _close(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None


def resample_to(samples: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """线性插值重采样（够用且零依赖，避免为此引入 scipy）。"""
    if samples is None or len(samples) == 0 or src_rate == dst_rate:
        return np.asarray(samples, dtype=np.float32).reshape(-1)
    audio = np.asarray(samples, dtype=np.float32).reshape(-1)
    dst_len = int(round(len(audio) * dst_rate / src_rate))
    if dst_len <= 0:
        return np.zeros(0, dtype=np.float32)
    src_idx = np.linspace(0, len(audio) - 1, dst_len, dtype=np.float64)
    left = np.floor(src_idx).astype(np.int64)
    right = np.minimum(left + 1, len(audio) - 1)
    frac = (src_idx - left).astype(np.float32)
    return (audio[left] * (1 - frac) + audio[right] * frac).astype(np.float32)


def list_input_devices() -> list[dict]:
    """列出可用输入设备，便于用户在 config.json 里指定。"""
    try:
        import sounddevice as sd
    except ImportError:  # pragma: no cover
        return []
    out = []
    for idx, dev in enumerate(sd.query_devices()):
        if dev.get("max_input_channels", 0) > 0:
            out.append({
                "index": idx,
                "name": dev.get("name", ""),
                "channels": dev.get("max_input_channels"),
                "default_samplerate": dev.get("default_samplerate"),
            })
    return out


def default_input_name() -> Optional[str]:
    try:
        import sounddevice as sd
        dev = sd.query_devices(kind="input")
        return dev.get("name")
    except Exception:
        return None
