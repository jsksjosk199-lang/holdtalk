# -*- coding: utf-8 -*-
"""ASR 端到端自测：读 wav → 重采样 16k → SenseVoice → 打印结果与耗时。"""
import os
import sys
import time
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from svime.asr import SenseVoiceEngine, clean_text, is_meaningful, trim_silence
from svime.audio import resample_to


def read_wav(path: str) -> tuple[np.ndarray, int]:
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        width = w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if width == 2:
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif width == 4:
        data = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        data = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
        data = (data - 128) / 128.0
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    return data, sr


def main() -> int:
    wav = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "test_zh.wav")
    if not os.path.isfile(wav):
        print(f"找不到音频：{wav}")
        return 2

    audio, sr = read_wav(wav)
    print(f"原始：{len(audio)/sr:.2f}s @ {sr}Hz")
    t0 = time.time()
    audio = resample_to(audio, sr, 16000)
    audio = trim_silence(audio, 16000)
    print(f"预处理：{len(audio)/16000:.2f}s（用时 {time.time()-t0:.2f}s）")

    engine = SenseVoiceEngine(
        model_dir=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "models", "sensevoice"),
        num_threads=2,
    )
    t1 = time.time()
    engine.load()
    print(f"模型加载：{time.time()-t1:.2f}s")

    t2 = time.time()
    text = engine.transcribe(audio, 16000)
    cost = time.time() - t2
    print(f"\n识别耗时：{cost:.2f}s（音频 {len(audio)/16000:.2f}s，RTF {cost/max(len(audio)/16000,0.01):.2f}）")
    print(f"识别结果：{text!r}")
    print(f"有效文本：{is_meaningful(text)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
