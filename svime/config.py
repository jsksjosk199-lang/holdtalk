# -*- coding: utf-8 -*-
"""配置加载：config.json 优先，缺项用默认值补齐。"""

from __future__ import annotations

import copy
import json
import os
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config.json")
CONFIG_EXAMPLE = os.path.join(ROOT, "config.example.json")

DEFAULTS: dict[str, Any] = {
    "asr": {
        "model_dir": "models/sensevoice",
        "num_threads": 2,
        "language": "zh",
        "use_itn": True,
        "warmup": True,
    },
    "trigger": {
        "long_press_ms": 350,
        "min_speech_ms": 250,
        "max_record_seconds": 60,
        "restore_middle_click": True,
        "beep": True,
    },
    "audio": {
        "device": None,
        "sample_rate": 16000,
    },
    "hotwords": {
        "enabled": True,
        "fuzzy": True,
        "list": [],
    },
    "polish": {
        "local_rules": True,
        "llm": {
            "enabled": False,
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "api_key_env": "SENSEVOICE_IME_API_KEY",
            "timeout": 25,
            "temperature": 0.2,
            "headers": {},
        },
    },
    "inject": {
        "method": "clipboard",
        "vim_mode": False,
        "restore_clipboard": True,
    },
    "log": {
        "level": "info",
        "file": "svime.log",
        "max_bytes": 1048576,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str | None = None) -> tuple[dict, str]:
    """返回 (配置, 实际使用的文件路径)。文件不存在时用默认值。"""
    target = path or CONFIG_PATH
    if not os.path.isfile(target):
        return copy.deepcopy(DEFAULTS), target
    with open(target, "r", encoding="utf-8-sig") as f:
        raw = json.load(f)
    return _deep_merge(DEFAULTS, raw), target


def resolve(path_value: str) -> str:
    """把配置里的相对路径按项目根目录解析。"""
    if not path_value:
        return path_value
    p = os.path.expanduser(str(path_value))
    return p if os.path.isabs(p) else os.path.join(ROOT, p)


def save_example(path: str = CONFIG_EXAMPLE) -> str:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(DEFAULTS, f, ensure_ascii=False, indent=2)
    return path
