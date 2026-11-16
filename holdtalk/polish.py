# -*- coding: utf-8 -*-
"""文本润色：本地规则去口水词，可选接大模型做二次理顺。

设计原则：
- 本地规则永远先跑，零成本、零延迟、离线；
- 大模型是「可选项」，默认关闭，密钥从环境变量读，绝不写进配置或仓库。
"""

from __future__ import annotations

import json
import os
import re
from typing import Optional

# 纯语气词：只有被标点/空白包住时才删（"啊"在"啊哈"里不能动）
INTERJECTIONS = ["嗯", "呃", "额", "啊", "唉", "哎"]

# 短语类填充：前面是句首/标点时删，后面紧跟实词时保留
SOFT_FILLERS = [
    "就是说", "然后就是", "就是呢", "然后呢", "其实吧", "反正吧",
    "怎么说呢", "你知道吧", "你懂我意思吧", "我跟你讲", "说白了吧",
    "这个", "那个",
]

# 句尾附属问句（"对不对""是吧"）：永远可删
TAIL_FILLERS = ["对吧", "是吧", "对不对", "好不好"]

# 这些词前面出现"这个/那个"时是实指，不能删："这个功能"≠废话
_DEMO_KEEP = ("功能", "东西", "问题", "时候", "地方", "事情", "人", "方案",
              "工具", "项目", "文件", "软件", "名单", "客户", "视频", "文章", "方案")

_BOUNDARY = r"[，。！？、,.!?；;\s]"
_LEAD = rf"(?:^|(?<={_BOUNDARY}))"
_TRAIL = rf"(?={_BOUNDARY}|$)"

_INTERJECTION_RE = re.compile(
    _LEAD + r"(?:" + "|".join(map(re.escape, INTERJECTIONS)) + r")" + _TRAIL
)
_SOFT_RE = re.compile(
    _LEAD + r"(?:" + "|".join(map(re.escape, SOFT_FILLERS)) + r")"
    r"(?!" + "|".join(map(re.escape, _DEMO_KEEP)) + r")"
)
_TAIL_RE = re.compile(
    r"(?:" + "|".join(map(re.escape, TAIL_FILLERS)) + r")" + _TRAIL
)

_CJK_SPACE_RE = re.compile(r"(?<=[\u4e00-\u9fff])[ \t]+(?=[\u4e00-\u9fff])")
_DUP_RE = re.compile(r"([\u4e00-\u9fff])\1{2,}")  # 同一个字连说三次以上
_MULTI_PUNCT_RE = re.compile(r"([，。！？、,.!?])\1+")
_EMPTY_PUNCT_RE = re.compile(rf"{_BOUNDARY}*[，、,]{_BOUNDARY}*")


def clean_local(text: str, add_period: bool = True) -> str:
    """本地规则：去填充词、去中文间空格、压缩重复、整理标点。"""
    if not text:
        return ""
    out = text

    # 1. 句尾问句附属词先删（"……，对吧。" → "……。"）
    out = _TAIL_RE.sub("", out)

    # 2. 短语类填充（这个/那个/就是说……），保留后面接实词的情况
    for _ in range(3):
        new = _SOFT_RE.sub("", out)
        if new == out:
            break
        out = new

    # 3. 纯语气词
    for _ in range(3):
        new = _INTERJECTION_RE.sub("", out)
        if new == out:
            break
        out = new

    # 4. 清理被删空后残留的孤立标点
    out = re.sub(rf"{_BOUNDARY}*[，、,]{_BOUNDARY}*", lambda m: "，" if "，" in m.group(0) else "", out)
    out = re.sub(r"[，、,]{2,}", "，", out)
    out = re.sub(r"，\s*([。！？.!?])", r"\1", out)

    # 5. 中文之间的多余空格
    out = _CJK_SPACE_RE.sub("", out)
    out = re.sub(r"\s{2,}", " ", out)

    # 6. 重复压缩：「我我我」→「我」
    out = _DUP_RE.sub(r"\1", out)
    out = re.sub(r"([\u4e00-\u9fff]{2,4})\1{1,}", r"\1", out)

    # 7. 首尾清理
    out = _MULTI_PUNCT_RE.sub(r"\1", out)
    out = re.sub(rf"^{_BOUNDARY}+", "", out)
    out = out.strip()
    out = re.sub(r"[，、,\s]+$", "", out)

    if add_period and out and out[-1] not in "。！？.!?…":
        out += "。"

    return out


LLM_SYSTEM_PROMPT = (
    "你是一个语音转写润色器。用户会给你一段语音识别的原始文本（可能有口水词、"
    "重复、断句错误、同音错字）。你的任务是把它整理成通顺、口语自然、可直接使用的文字。\n"
    "硬性要求：\n"
    "1. 只输出整理后的正文，不要任何解释、前言、引号或 Markdown；\n"
    "2. 严格保留原意，不增加原文没有的信息，不扩写，不总结；\n"
    "3. 删掉「嗯、啊、那个、就是说」这类填充词，修正明显同音错字；\n"
    "4. 保持说话人的语气和用词习惯，不要改成书面语或官腔；\n"
    "5. 如果原文已经是干净的句子，就原样返回，不要为了改而改。"
)


class LlmPolisher:
    """OpenAI 兼容接口的润色器（DeepSeek / 通义 / 智谱 / Ollama 都能用）。"""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key_env: str = "SENSEVOICE_IME_API_KEY",
        timeout: float = 25.0,
        extra_headers: Optional[dict] = None,
        temperature: float = 0.2,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key_env = api_key_env
        self.timeout = float(timeout)
        self.extra_headers = extra_headers or {}
        self.temperature = float(temperature)

    @property
    def api_key(self) -> str:
        return os.environ.get(self.api_key_env, "").strip()

    @property
    def available(self) -> bool:
        # 本地 Ollama 之类可以不要 key
        return bool(self.base_url) and (bool(self.api_key) or "127.0.0.1" in self.base_url
                                        or "localhost" in self.base_url)

    def polish(self, text: str, context: str = "") -> str:
        if not text or not self.available:
            return text
        import urllib.error
        import urllib.request

        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": LLM_SYSTEM_PROMPT},
                {"role": "user", "content": (context + text) if context else text},
            ],
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                **self.extra_headers,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            content = (body.get("choices") or [{}])[0].get("message", {}).get("content", "")
            content = (content or "").strip()
            return content or text
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError, OSError):
            # 润色失败绝不能丢原文
            return text


def load_polisher(cfg: dict) -> Optional[LlmPolisher]:
    p = ((cfg or {}).get("polish") or {}).get("llm") or {}
    if not p.get("enabled"):
        return None
    polisher = LlmPolisher(
        base_url=p.get("base_url", ""),
        model=p.get("model", ""),
        api_key_env=p.get("api_key_env", "SENSEVOICE_IME_API_KEY"),
        timeout=p.get("timeout", 25),
        extra_headers=p.get("headers") or {},
        temperature=p.get("temperature", 0.2),
    )
    return polisher if polisher.available else None
