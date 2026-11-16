# -*- coding: utf-8 -*-
"""热词纠错：把 ASR 常见的错识别拉回正确写法。

两条通道：
1. 别名精确替换 —— 你自己写死的错法，命中率 100%，最可控；
2. 模糊匹配 —— 中文走拼音音节编辑距离，英文/混合走字母相似度，
   专门收拾那些"没被 aliases 覆盖到"的音近错误。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Iterable, Optional

try:
    from pypinyin import Style, lazy_pinyin
    _HAS_PYPINYIN = True
except ImportError:  # pragma: no cover
    _HAS_PYPINYIN = False


_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.\-+]*|\d+[\w.\-]*")


def _syllables(text: str) -> list[str]:
    """把一个中文字串拆成无声调拼音音节；非中文字符原样保留成小写。"""
    if not _HAS_PYPINYIN:
        return [c.lower() for c in text]
    out: list[str] = []
    for chunk in re.findall(r"[\u4e00-\u9fff]+|[^\u4e00-\u9fff]+", text):
        if _CJK_RE.match(chunk[0]):
            out.extend(lazy_pinyin(chunk, style=Style.NORMAL, errors="ignore"))
        else:
            out.append(chunk.strip().lower())
    return [s for s in out if s]


def _edit_distance(a: list[str], b: list[str]) -> int:
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(
                prev[j] + 1,          # 删除
                cur[j - 1] + 1,       # 插入
                prev[j - 1] + (ca != cb),  # 替换
            ))
        prev = cur
    return prev[-1]


@dataclass
class HotwordEntry:
    word: str
    aliases: list[str] = field(default_factory=list)
    fuzzy: bool = True

    @property
    def syllables(self) -> list[str]:
        return _syllables(self.word)

    @property
    def is_cjk(self) -> bool:
        return bool(_CJK_RE.search(self.word))


@dataclass
class Hit:
    start: int
    end: int
    source: str
    target: str
    kind: str  # "alias" | "fuzzy-en" | "fuzzy-cjk"


class HotwordCorrector:
    def __init__(self, entries: Iterable[dict], fuzzy: bool = True) -> None:
        self.entries: list[HotwordEntry] = []
        for raw in entries or []:
            if isinstance(raw, str):
                raw = {"word": raw}
            word = (raw.get("word") or "").strip()
            if not word:
                continue
            aliases = [a.strip() for a in raw.get("aliases", []) if a and a.strip()]
            self.entries.append(HotwordEntry(
                word=word,
                aliases=aliases,
                fuzzy=bool(raw.get("fuzzy", True)),
            ))
        self.fuzzy = bool(fuzzy)

        # 别名 → 正名 的查找表（小写键）
        self._alias_map: list[tuple[str, str]] = []
        for e in self.entries:
            for a in e.aliases:
                self._alias_map.append((a, e.word))
        # 长别名优先，避免短别名先吃掉长别名的一部分
        self._alias_map.sort(key=lambda p: len(p[0]), reverse=True)

    # ---------------- 主入口 ----------------
    def correct(self, text: str) -> tuple[str, list[Hit]]:
        if not text:
            return text, []

        hits: list[Hit] = []

        # 第一轮：别名精确替换（不区分大小写的字面替换）
        lowered = text.lower()
        for alias, word in self._alias_map:
            start = 0
            al = alias.lower()
            while True:
                idx = lowered.find(al, start)
                if idx < 0:
                    break
                hits.append(Hit(idx, idx + len(alias), text[idx:idx + len(alias)], word, "alias"))
                start = idx + len(al)

        # 第二轮：模糊匹配（先收集候选，再冲突消解）
        if self.fuzzy:
            hits.extend(self._fuzzy_en_candidates(text))
            hits.extend(self._fuzzy_cjk_candidates(text))

        if not hits:
            return text, []

        # 冲突消解：按"长度优先 → 别名优先 → 起点靠前"挑不重叠的
        kind_rank = {"alias": 0, "fuzzy-en": 1, "fuzzy-cjk": 2}
        hits.sort(key=lambda h: (-(h.end - h.start), kind_rank[h.kind], h.start))
        chosen: list[Hit] = []
        for h in hits:
            if all(h.end <= c.start or h.start >= c.end for c in chosen):
                chosen.append(h)

        chosen.sort(key=lambda h: h.start, reverse=True)
        out = text
        for h in chosen:
            out = out[:h.start] + h.target + out[h.end:]
        return out, chosen

    # ---------------- 英文 / 中英混合 ----------------
    def _fuzzy_en_candidates(self, text: str) -> list[Hit]:
        hits: list[Hit] = []
        tokens = list(_TOKEN_RE.finditer(text))
        for e in self.entries:
            if not e.fuzzy or e.is_cjk:
                continue
            target_norm = re.sub(r"[^a-z0-9]", "", e.word.lower())
            if len(target_norm) < 4:
                continue
            # 单 token 与 双 token（如 claude code）
            for span in (1, 2):
                for i in range(len(tokens) - span + 1):
                    group = tokens[i:i + span]
                    raw = text[group[0].start():group[-1].end()]
                    norm = re.sub(r"[^a-z0-9]", "", raw.lower())
                    if len(norm) < 3:
                        continue
                    ratio = SequenceMatcher(None, norm, target_norm).ratio()
                    # 拼写接近、或去掉空格/符号后完全一致（Work Buddy → WorkBuddy）都算命中
                    if (ratio >= 0.84 or norm == target_norm) and raw != e.word:
                        hits.append(Hit(group[0].start(), group[-1].end(), raw, e.word, "fuzzy-en"))
        return hits

    # ---------------- 中文（拼音） ----------------
    def _fuzzy_cjk_candidates(self, text: str) -> list[Hit]:
        if not _HAS_PYPINYIN:
            return []
        hits: list[Hit] = []
        cjk_spans = [(m.start(), m.end()) for m in re.finditer(r"[\u4e00-\u9fff]+", text)]

        for e in self.entries:
            if not e.fuzzy or not e.is_cjk:
                continue
            target = e.syllables
            n = len(target)
            # 太短的词做模糊匹配误伤率极高（"豆包"→"书包"），只认精确/别名
            if n < 3 or e.word in text:
                continue
            allow = max(1, n // 4)

            for s_start, s_end in cjk_spans:
                span_text = text[s_start:s_end]
                span_len = len(span_text)
                # 窗口长度严格等于热词字数：放宽到 ±1 会多吃掉旁边的字
                # （「用图八工具箱」被当成一个整体替换，结果弄丢了「用」）
                if span_len < n:
                    continue
                for i in range(0, span_len - n + 1):
                    piece = span_text[i:i + n]
                    syl = _syllables(piece)
                    if len(syl) != n:
                        continue
                    dist = _edit_distance(syl, target)
                    # dist == 0 就是纯同音字错误（图八→图吧），才是最常见的场景
                    if dist <= allow:
                        hits.append(Hit(s_start + i, s_start + i + n, piece, e.word, "fuzzy-cjk"))
        return hits


def load_corrector(cfg: dict) -> Optional[HotwordCorrector]:
    hw = (cfg or {}).get("hotwords") or {}
    if not hw.get("enabled", True):
        return None
    return HotwordCorrector(hw.get("list") or [], fuzzy=hw.get("fuzzy", True))
