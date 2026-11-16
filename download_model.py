# -*- coding: utf-8 -*-
"""下载 SenseVoice 离线识别模型（sherpa-onnx int8 量化版，约 230MB）。

用法：
    python download_model.py                 # 默认走 hf-mirror（国内快）
    python download_model.py --source hf     # 走 huggingface 官方
    python download_model.py --proxy http://127.0.0.1:7897
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.request

REPO = "csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
FILES = [
    ("model.int8.onnx", 239233841),
    ("tokens.txt", 315894),
]
MIRRORS = {
    "hf-mirror": f"https://hf-mirror.com/{REPO}/resolve/main/",
    "hf": f"https://huggingface.co/{REPO}/resolve/main/",
}

ROOT = os.path.dirname(os.path.abspath(__file__))
DEST = os.path.join(ROOT, "models", "sensevoice")


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def download(url: str, dest: str, expect: int = 0, proxy: str | None = None) -> None:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    if os.path.isfile(dest) and (expect == 0 or os.path.getsize(dest) == expect):
        print(f"  已存在，跳过：{os.path.basename(dest)}")
        return

    req = urllib.request.Request(url, headers={"User-Agent": "sensevoice-ime/1.0"})
    if proxy:
        handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        opener = urllib.request.build_opener(handler)
    else:
        opener = urllib.request.build_opener()

    print(f"  下载 {os.path.basename(dest)} ...")
    t0 = time.time()
    with opener.open(req, timeout=60) as resp, open(tmp, "wb") as f:
        total = int(resp.headers.get("Content-Length") or expect or 0)
        got = 0
        last = 0.0
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            now = time.time()
            if now - last > 0.5:
                last = now
                pct = f"{got/total*100:5.1f}%" if total else "  ?  "
                speed = got / max(now - t0, 0.01)
                sys.stdout.write(f"\r    {pct} {human(got)} / {human(total)}  {human(speed)}/s")
                sys.stdout.flush()
    print()
    os.replace(tmp, dest)
    size = os.path.getsize(dest)
    if expect and size != expect:
        print(f"  ⚠ 大小不符：{size} != {expect}，文件可能不完整")
    else:
        print(f"  完成：{human(size)}")


def main() -> int:
    ap = argparse.ArgumentParser(description="下载 SenseVoice ONNX 模型")
    ap.add_argument("--source", default="hf-mirror", choices=list(MIRRORS), help="下载源")
    ap.add_argument("--proxy", default=os.environ.get("HTTPS_PROXY") or None,
                    help="HTTP 代理，例如 http://127.0.0.1:7897")
    ap.add_argument("--dest", default=DEST, help="模型存放目录")
    args = ap.parse_args()

    base = MIRRORS[args.source]
    print(f"模型目录：{args.dest}")
    print(f"下载源：{args.source}  ({base.split('/')[2]})")
    if args.proxy:
        print(f"代理：{args.proxy}")

    for name, size in FILES:
        download(base + name, os.path.join(args.dest, name), size, args.proxy)

    print("\n完成。模型文件：")
    for name, _ in FILES:
        p = os.path.join(args.dest, name)
        print(f"  {p}  ({human(os.path.getsize(p)) if os.path.isfile(p) else '缺失'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
