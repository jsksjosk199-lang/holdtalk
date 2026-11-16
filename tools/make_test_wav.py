# -*- coding: utf-8 -*-
"""用系统 SAPI 合成一段中文测试音频（仅用于自测，不参与运行时）。"""
import os
import sys
import wave

import win32com.client

TEXT = "嗯，那个，我今天想跟你讲一下，就是说 WorkBuddy 这个工具其实挺好用的，然后我们再看看千问和豆包。"
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "test_zh.wav")

voice = win32com.client.Dispatch("SAPI.SpVoice")
stream = win32com.client.Dispatch("SAPI.SpFileStream")

# 16kHz / 16bit / mono
fmt = win32com.client.Dispatch("SAPI.SpAudioFormat")
fmt.Type = 22  # SAFT16kHz16BitMono
stream.Format = fmt
stream.Open(OUT, 3)
voice.AudioOutputStream = stream

voices = voice.GetVoices()
zh = None
for i in range(voices.Count):
    v = voices.Item(i)
    desc = v.GetDescription()
    if "Chinese" in desc or "中文" in desc:
        zh = v
        break
if zh is None and voices.Count:
    zh = voices.Item(0)
voice.Voice = zh
print("使用语音:", zh.GetDescription() if zh else "default")
voice.Speak(TEXT, 0)
stream.Close()

with wave.open(OUT, "rb") as w:
    print("输出:", OUT, f"{w.getnframes()/w.getframerate():.2f}s",
          w.getframerate(), "Hz", w.getnchannels(), "ch", w.getsampwidth() * 8, "bit")
