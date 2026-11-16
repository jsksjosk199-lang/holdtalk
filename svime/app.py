# -*- coding: utf-8 -*-
"""主流程编排：按下录音 → 松开识别 → 热词纠错 → 润色 → 回填光标。"""

from __future__ import annotations

import logging
import logging.handlers
import os
import threading
import time
from typing import Optional

import numpy as np

from . import config as cfg_mod
from .asr import SenseVoiceEngine, is_meaningful, trim_silence
from .audio import Recorder
from .hook import MiddleHoldHook, acquire_single_instance
from .hotwords import load_corrector
from .inject import beep, paste_text
from .polish import clean_local, load_polisher

log = logging.getLogger("svime")


def setup_logging(cfg: dict) -> None:
    lc = cfg.get("log") or {}
    level = getattr(logging, str(lc.get("level", "info")).upper(), logging.INFO)
    log.setLevel(level)
    log.handlers.clear()

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")

    # pythonw 下没有控制台，加 handler 会抛异常，必须判断
    import sys
    if sys.stderr is not None:
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(fmt)
        log.addHandler(sh)

    log_file = cfg_mod.resolve(lc.get("file", "svime.log"))
    try:
        fh = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=int(lc.get("max_bytes", 1048576)),
            backupCount=2, encoding="utf-8")
        fh.setFormatter(fmt)
        log.addHandler(fh)
    except Exception:
        pass


class VoiceImeApp:
    def __init__(self, config_path: Optional[str] = None) -> None:
        self.cfg, self.config_path = cfg_mod.load_config(config_path)
        setup_logging(self.cfg)

        a = self.cfg["asr"]
        self.engine = SenseVoiceEngine(
            model_dir=cfg_mod.resolve(a["model_dir"]),
            num_threads=a.get("num_threads", 2),
            language=a.get("language", "zh"),
            use_itn=a.get("use_itn", True),
        )
        self.corrector = load_corrector(self.cfg)
        self.polisher = load_polisher(self.cfg)

        au = self.cfg["audio"]
        self.recorder = Recorder(
            sample_rate=int(au.get("sample_rate", 16000)),
            device=au.get("device"),
        )

        tr = self.cfg["trigger"]
        self.max_seconds = float(tr.get("max_record_seconds", 60))
        self.min_speech_ms = int(tr.get("min_speech_ms", 250))
        self.want_beep = bool(tr.get("beep", True))

        self._processing = threading.Lock()
        self._watchdog: Optional[threading.Timer] = None
        self._idle = threading.Event()
        self._idle.set()

        self.hook = MiddleHoldHook(
            threshold_ms=int(tr.get("long_press_ms", 350)),
            on_hold_start=self.on_hold_start,
            on_hold_end=self.on_hold_end,
            restore_middle_click=bool(tr.get("restore_middle_click", True)),
            logger=log.info,
        )

    # ---------------- 录音控制 ----------------
    def on_hold_start(self) -> None:
        try:
            if not self._processing.acquire(blocking=False):
                log.info("[skip] 上一段还在处理，忽略本次触发")
                return
            if not self._idle.is_set():
                log.info("[skip] 上一段还没结束")
                self._processing.release()
                return
            self._idle.clear()
            self.recorder.start()
            if self.want_beep:
                beep(1200, 40)
            log.info("[rec] 开始录音")
            # 超长保护：录到上限自动收尾
            self._watchdog = threading.Timer(self.max_seconds, self._force_stop)
            self._watchdog.daemon = True
            self._watchdog.start()
        except Exception as exc:
            log.error(f"[rec] 启动录音失败: {exc}")
            self._idle.set()
            self._processing.release()

    def _force_stop(self) -> None:
        if self.recorder.recording:
            log.warning(f"[rec] 达到 {self.max_seconds:.0f}s 上限，自动结束")
            self._finish()

    def on_hold_end(self) -> None:
        self._finish()

    def _finish(self) -> None:
        if self._watchdog is not None:
            self._watchdog.cancel()
            self._watchdog = None
        try:
            duration = self.recorder.duration
            audio = self.recorder.stop()
        except Exception as exc:
            log.error(f"[rec] 停止录音失败: {exc}")
            audio, duration = np.zeros(0, dtype=np.float32), 0.0

        if self.want_beep:
            beep(900, 40)
        log.info(f"[rec] 结束，{len(audio)/16000:.2f}s")

        if len(audio) / 16000 * 1000 < self.min_speech_ms:
            log.info("[skip] 太短，可能是误触")
            self._release()
            return

        t = threading.Thread(target=self._process, args=(audio,), daemon=True)
        t.start()

    def _release(self) -> None:
        self._idle.set()
        try:
            self._processing.release()
        except RuntimeError:
            pass

    # ---------------- 识别 + 输出 ----------------
    def _process(self, audio: np.ndarray) -> None:
        t0 = time.time()
        try:
            audio = trim_silence(audio, 16000)
            if len(audio) < 1600:  # 不足 100ms，基本是静音
                log.info("[skip] 有效语音过短")
                return

            t_asr = time.time()
            text = self.engine.transcribe(audio, 16000)
            log.info(f"[asr] {time.time()-t_asr:.2f}s -> {text!r}")
            if not is_meaningful(text):
                log.info("[skip] 识别结果无有效内容")
                return

            if self.corrector is not None:
                text, hits = self.corrector.correct(text)
                if hits:
                    log.info("[hotword] " + ", ".join(f"{h.source}→{h.target}" for h in hits))

            if self.cfg["polish"].get("local_rules", True):
                text = clean_local(text)

            if self.polisher is not None:
                t_llm = time.time()
                text = self.polisher.polish(text)
                log.info(f"[llm] {time.time()-t_llm:.2f}s -> {text!r}")

            if not text.strip():
                log.info("[skip] 润色后为空")
                return

            ij = self.cfg["inject"]
            ok = paste_text(
                text,
                method=ij.get("method", "clipboard"),
                vim_mode=bool(ij.get("vim_mode", False)),
                restore_clipboard=bool(ij.get("restore_clipboard", True)),
            )
            log.info(f"[out] {'已输入' if ok else '输入失败'} | 总耗时 {time.time()-t0:.2f}s | {text}")
        except Exception as exc:
            log.exception(f"[error] 处理失败: {exc}")
        finally:
            self._release()

    # ---------------- 生命周期 ----------------
    def warmup(self) -> None:
        if not self.cfg["asr"].get("warmup", True):
            return
        try:
            t0 = time.time()
            self.engine.load()
            log.info(f"[asr] 模型预热完成，{time.time()-t0:.2f}s")
        except Exception as exc:
            log.error(f"[asr] 预热失败: {exc}")

    def run(self) -> int:
        mutex = acquire_single_instance()
        if mutex is None:
            log.error("已有一个实例在运行，本次退出（避免一条录音被处理两遍）")
            return 3

        log.info("=" * 56)
        log.info("  SenseVoice IME 启动")
        log.info(f"  长按中键 {self.cfg['trigger']['long_press_ms']}ms = 语音输入")
        log.info(f"  热词 {len(self.corrector.entries) if self.corrector else 0} 条 | "
                 f"润色 {'本地' if self.cfg['polish'].get('local_rules') else '关闭'}"
                 f"{' + 大模型' if self.polisher else ''}")
        log.info("=" * 56)

        self.warmup()
        try:
            self.hook.run()
        finally:
            self.recorder.cancel()
        return 0
