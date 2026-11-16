# -*- coding: utf-8 -*-
"""开机自启：在启动文件夹里放一个 vbs，静默拉起（不弹黑框）。

    python tools/setup_autostart.py           安装
    python tools/setup_autostart.py --remove  卸载
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STARTUP = os.path.join(os.environ["APPDATA"], r"Microsoft\Windows\Start Menu\Programs\Startup")
VBS = os.path.join(STARTUP, "SenseVoiceIME.vbs")

VBS_TEMPLATE = '''Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "{root}"
sh.Run """{pyw}"" ""{main}""", 0, False
'''


def find_pythonw() -> str:
    """优先用和当前解释器同目录的 pythonw.exe。"""
    exe = sys.executable
    cand = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.isfile(cand):
        return cand
    found = shutil.which("pythonw") or shutil.which("pythonw.exe")
    if found:
        return found
    raise SystemExit("找不到 pythonw.exe，请确认 Python 已正确安装")


def install() -> int:
    os.makedirs(STARTUP, exist_ok=True)
    pyw = find_pythonw()
    main = os.path.join(ROOT, "main.py")
    with open(VBS, "w", encoding="utf-16") as f:  # VBS 用 UTF-16 最稳
        f.write(VBS_TEMPLATE.format(root=ROOT, pyw=pyw, main=main))

    # 立刻拉起一份，不用等重启
    subprocess.Popen([pyw, main], cwd=ROOT,
                     creationflags=0x00000008)  # DETACHED_PROCESS

    print("已设置开机自启：")
    print(f"  {VBS}")
    print(f"  启动命令：{pyw} {main}")
    print("\n已尝试在后台启动一次，长按鼠标中键试试。")
    return 0


def remove() -> int:
    if os.path.isfile(VBS):
        os.remove(VBS)
        print(f"已移除自启项：{VBS}")
    else:
        print("没有找到自启项，无需移除")
    print("正在运行的实例请在任务管理器里结束 pythonw.exe。")
    return 0


if __name__ == "__main__":
    raise SystemExit(remove() if "--remove" in sys.argv else install())
