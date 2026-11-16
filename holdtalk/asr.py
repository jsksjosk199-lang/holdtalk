# -*- coding: utf-8 -*-
"""SenseVoice 离线语音识别引擎（sherpa-onnx，纯 CPU，无需 PyTorch）。"""

from __future__ import annotations

import os
import re
import threading
import time
from typing import Optional

import numpy as np

# SenseVoice 输出的富文本标签，例如 <|zh|><|NEUTRAL|><|Speech|><|woitn|>
_TAG_RE = re.compile(r"<\|[^|]*\|>")


class AsrError(RuntimeError):
    pass


class SenseVoiceEngine:
    """线程安全的懒加载封装：第一次识别时初始化，之后复用。"""

    def __init__(
        self,
        model_dir: str,
        num_threads: int = 2,
        language: str = "zh",
        use_itn: bool = True,
    ) -> None:
        self.model_dir = os.path.abspath(model_dir)
        self.num_threads = max(1, int(num_threads))
        self.language = language
        self.use_itn = bool(use_itn)

        self._recognizer = None
        self._lock = threading.Lock()
        self._load_seconds: Optional[float] = None

    # ---------------- 模型文件定位 ----------------
    def _find(self, *names: str) -> str:
        for name in names:
            p = os.path.join(self.model_dir, name)
            if os.path.isfile(p):
                return p
        raise AsrError(
            f"在 {self.model_dir} 下找不到模型文件（期望其一：{', '.join(names)}）。"
            f"请先运行 python download_model.py 下载模型。"
        )

    @property
    def model_path(self) -> str:
        return self._find("model.int8.onnx", "model.onnx")

    @property
    def tokens_path(self) -> str:
        return self._find("tokens.txt")

    # ---------------- 初始化 ----------------
    def load(self) -> None:
        if self._recognizer is not None:
            return
        with self._lock:
            if self._recognizer is not None:
                return
            try:
                import sherpa_onnx
            except ImportError as exc:  # pragma: no cover
                raise AsrError(
                    "缺少 sherpa-onnx，请先执行：pip install sherpa-onnx"
                ) from exc

            t0 = time.time()
            kw = dict(
                model=self.model_path,
                tokens=self.tokens_path,
                num_threads=self.num_threads,
                use_itn=self.use_itn,
                debug=False,
            )
            # 不同版本参数名略有差异，做一次兼容
            try:
                self._recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                    language=self.language, **kw
                )
            except TypeError:
                kw.pop("language", None)
                self._recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(**kw)
            self._load_seconds = time.time() - t0

    @property
    def load_seconds(self) -> Optional[float]:
        return self._load_seconds

    # ---------------- 识别 ----------------
    def transcribe(self, samples: np.ndarray, sample_rate: int = 16000) -> str:
        """samples: float32 mono，取值范围 [-1, 1]。返回清洗后的纯文本。"""
        if samples is None or len(samples) == 0:
            return ""
        self.load()
        audio = np.asarray(samples, dtype=np.float32).reshape(-1)

        stream = self._recognizer.create_stream()
        stream.accept_waveform(int(sample_rate), audio)
        self._recognizer.decode_stream(stream)
        raw = getattr(stream.result, "text", "") or ""
        return clean_text(raw)


def clean_text(raw: str) -> str:
    """去掉 SenseVoice 的标签与多余空白。"""
    text = _TAG_RE.sub("", raw or "")
    text = text.replace("▁", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def is_meaningful(text: str, min_chars: int = 1) -> bool:
    """过滤掉纯标点/空白这类无效识别结果。"""
    return len(re.sub(r"[\s\W_]+", "", text or "")) >= min_chars


def trim_silence(samples: np.ndarray, sample_rate: int = 16000,
                 threshold: float = 0.008, pad_ms: int = 120) -> np.ndarray:
    """按能量裁剪首尾静音，避免 VAD 缺失时把整段静音喂给模型。"""
    if samples is None or len(samples) == 0:
        return samples
    audio = np.asarray(samples, dtype=np.float32).reshape(-1)
    win = max(1, int(sample_rate * 0.02))  # 20ms
    n = len(audio) // win
    if n == 0:
        return audio
    frames = audio[: n * win].reshape(n, win)
    energy = np.sqrt((frames ** 2).mean(axis=1))
    active = np.where(energy > threshold)[0]
    if active.size == 0:
        return np.zeros(0, dtype=np.float32)
    pad = int(sample_rate * pad_ms / 1000)
    start = max(0, active[0] * win - pad)
    end = min(len(audio), (active[-1] + 1) * win + pad)
    return audio[start:end]
