# -*- coding: utf-8 -*-
"""SenseVoice IME 命令行入口。

    python main.py                 启动（长按鼠标中键说话）
    python main.py --devices       查看可用麦克风
    python main.py --test          录 4 秒，直接看识别效果（不注入）
    python main.py --file x.wav    转写一个音频文件
"""

from __future__ import annotations

import argparse
import os
import sys
import time

if sys.stdout is None or sys.stderr is None:  # pythonw 启动时没有控制台
    _d = os.path.join(os.path.expanduser("~"), ".sensevoice-ime")
    os.makedirs(_d, exist_ok=True)
    if sys.stdout is None:
        sys.stdout = open(os.path.join(_d, "stdout.log"), "a", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.path.join(_d, "stderr.log"), "a", encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from svime import config as cfg_mod  # noqa: E402
from svime.asr import SenseVoiceEngine, is_meaningful, trim_silence  # noqa: E402
from svime.audio import Recorder, list_input_devices, resample_to  # noqa: E402
from svime.hotwords import load_corrector  # noqa: E402
from svime.polish import clean_local, load_polisher  # noqa: E402


def cmd_devices() -> int:
    devs = list_input_devices()
    if not devs:
        print("没有找到可用麦克风（sounddevice 可能未安装）")
        return 1
    print(f"{'索引':<5}{'名称':<48}{'声道':<6}默认采样率")
    for d in devs:
        print(f"{d['index']:<6}{d['name'][:46]:<48}{d['channels']:<6}{d['default_samplerate']:.0f}")
    print("\n想固定用某个设备，把索引填进 config.json 的 audio.device")
    return 0


def cmd_test(config_path: str | None) -> int:
    cfg, _ = cfg_mod.load_config(config_path)
    au = cfg["audio"]
    rec = Recorder(sample_rate=int(au.get("sample_rate", 16000)), device=au.get("device"))
    engine = SenseVoiceEngine(
        model_dir=cfg_mod.resolve(cfg["asr"]["model_dir"]),
        num_threads=cfg["asr"].get("num_threads", 2),
        use_itn=cfg["asr"].get("use_itn", True),
    )
    print("加载模型…")
    engine.load()

    print("请说话（4 秒）…")
    rec.start()
    time.sleep(4)
    audio = rec.stop()
    print(f"录到 {len(audio)/16000:.2f}s")

    audio = trim_silence(audio, 16000)
    t0 = time.time()
    text = engine.transcribe(audio, 16000)
    print(f"识别（{time.time()-t0:.2f}s）：{text!r}")

    if not is_meaningful(text):
        print("没识别出有效内容")
        return 2

    corrector = load_corrector(cfg)
    if corrector is not None:
        text2, hits = corrector.correct(text)
        if hits:
            print("热词：" + ", ".join(f"{h.source}→{h.target}" for h in hits))
        text = text2

    if cfg["polish"].get("local_rules", True):
        text = clean_local(text)

    polisher = load_polisher(cfg)
    if polisher is not None:
        print("大模型润色中…")
        text = polisher.polish(text)
    else:
        if cfg["polish"]["llm"].get("enabled"):
            print(f"（大模型已启用但缺少 API Key：环境变量 "
                  f"{cfg['polish']['llm'].get('api_key_env')}）")

    print(f"\n最终结果：{text}")
    return 0


def cmd_file(path: str, config_path: str | None) -> int:
    import wave

    import numpy as np

    cfg, _ = cfg_mod.load_config(config_path)
    with wave.open(path, "rb") as w:
        sr, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if width == 2:
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    else:
        data = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    data = resample_to(data, sr, 16000)
    data = trim_silence(data, 16000)

    engine = SenseVoiceEngine(
        model_dir=cfg_mod.resolve(cfg["asr"]["model_dir"]),
        num_threads=cfg["asr"].get("num_threads", 2),
        use_itn=cfg["asr"].get("use_itn", True),
    )
    t0 = time.time()
    text = engine.transcribe(data, 16000)
    print(f"识别（{time.time()-t0:.2f}s）：{text!r}")

    corrector = load_corrector(cfg)
    if corrector is not None:
        text, hits = corrector.correct(text)
        if hits:
            print("热词：" + ", ".join(f"{h.source}→{h.target}" for h in hits))
    if cfg["polish"].get("local_rules", True):
        text = clean_local(text)
    polisher = load_polisher(cfg)
    if polisher is not None:
        text = polisher.polish(text)
    print(f"最终结果：{text}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="SenseVoice IME —— 长按鼠标中键，本地离线语音输入")
    ap.add_argument("--config", help="配置文件路径（默认项目根目录 config.json）")
    ap.add_argument("--devices", action="store_true", help="列出麦克风设备")
    ap.add_argument("--test", action="store_true", help="录 4 秒测试识别效果")
    ap.add_argument("--file", help="转写指定 wav 文件")
    args = ap.parse_args()

    if args.devices:
        return cmd_devices()
    if args.test:
        return cmd_test(args.config)
    if args.file:
        return cmd_file(args.file, args.config)

    from svime.app import VoiceImeApp
    return VoiceImeApp(args.config).run()


if __name__ == "__main__":
    raise SystemExit(main())
