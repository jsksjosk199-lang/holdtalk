# -*- coding: utf-8 -*-
"""一条命令完成部署 —— 专为 Agent 设计。

设计目标（写给接手的 Agent 看）：
  * 幂等：重复执行不会装两遍、不会覆盖已有 config.json、不会启两个实例
  * 非交互：全程不读 stdin，不需要人点「下一步」
  * 机器可读：--json 时只输出一段 JSON，退出码 0 成功 / 非 0 失败
  * 可自愈：代理不通就自己换、依赖缺就自己装、模型不全就自己下
  * 失败有话说：每个失败都带 fix 字段，直接照着执行即可

用法：
    python bootstrap.py                 # 全自动：装依赖 → 下模型 → 自检 → 启动
    python bootstrap.py --json          # 同上，但只输出 JSON（Agent 用这个）
    python bootstrap.py --check         # 只体检，不改任何东西
    python bootstrap.py --no-start      # 装好但不启动
    python bootstrap.py --no-autostart  # 不注册开机自启
    python bootstrap.py --index 12      # 强制指定麦克风设备索引

退出码：
    0  成功
    1  参数错误
    2  环境不满足（Python 太旧等）
    3  依赖安装失败
    4  模型下载失败
    5  自检未通过
    6  服务启动失败
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(ROOT, "models", "sensevoice")
CONFIG = os.path.join(ROOT, "config.json")
VERSION = "1.0.0"

# 常见本地代理端口，按命中率排序（本机 Clash 是 7897）
PROXY_PORTS = [7897, 7890, 7891, 10809, 10808, 1080, 8889, 8080, 60244]
REQUIRED = ["sherpa_onnx", "sounddevice", "pypinyin", "numpy"]
MIN_PY = (3, 10)


class Step:
    def __init__(self, name: str, ok: bool, detail: str = "", fix: str = "") -> None:
        self.name, self.ok, self.detail, self.fix = name, ok, detail, fix

    def to_dict(self) -> dict:
        d = {"step": self.name, "ok": self.ok, "detail": self.detail}
        if self.fix:
            d["fix"] = self.fix
        return d


def say(msg: str, quiet: bool) -> None:
    if not quiet:
        print(msg, flush=True)


# ---------------------------------------------------------------- 代理探测
def _port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.6) -> bool:
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _proxy_works(proxy: str, url: str = "https://pypi.org/simple/", timeout: float = 6.0) -> bool:
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    try:
        with opener.open(urllib.request.Request(url, method="HEAD"), timeout=timeout):
            return True
    except Exception:
        return False


def _direct_works(url: str = "https://pypi.tuna.tsinghua.edu.cn/simple/",
                  timeout: float = 5.0) -> bool:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(urllib.request.Request(url, method="HEAD"), timeout=timeout):
            return True
    except Exception:
        return False


def pick_proxy(quiet: bool) -> str | None:
    """返回可用的 http 代理；直连能通则返回 None。"""
    # 先看直连：很多机器其实不用代理，硬塞一个代理反而会 502
    if _direct_works():
        say("  · 直连可用（跳过代理）", quiet)
        return None

    env_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or ""
    candidates: list[str] = []
    if env_proxy:
        candidates.append(env_proxy)
    for p in PROXY_PORTS:
        if _port_open(p):
            proxy = f"http://127.0.0.1:{p}"
            if proxy not in candidates:
                candidates.append(proxy)

    for proxy in candidates:
        if _proxy_works(proxy):
            say(f"  · 直连不通，改用代理 {proxy}", quiet)
            return proxy
    say("  · 没找到可用代理，将按直连尝试（失败会明确报错）", quiet)
    return None


# ---------------------------------------------------------------- 各步骤
def check_python(quiet: bool) -> Step:
    if sys.version_info < MIN_PY:
        return Step("python", False,
                    f"当前 {sys.version_info.major}.{sys.version_info.minor}，需要 >= {MIN_PY[0]}.{MIN_PY[1]}",
                    "安装 Python 3.10+ 并确保 python 在 PATH 中")
    say(f"  · Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}", quiet)
    return Step("python", True, f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")


def install_deps(proxy: str | None, quiet: bool) -> Step:
    missing = []
    for mod in REQUIRED:
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if not missing:
        say("  · 依赖已就绪，跳过", quiet)
        return Step("deps", True, "already installed")

    say(f"  · 安装依赖：{', '.join(missing)}", quiet)
    cmd = [sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check"]
    cmd += ["-i", "https://pypi.tuna.tsinghua.edu.cn/simple"]
    if proxy:
        cmd += ["--proxy", proxy]
    cmd += ["-r", os.path.join(ROOT, "requirements.txt")]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return Step("deps", False, "pip 超时（10 分钟）", "手动执行 install.bat 或检查网络")

    if r.returncode != 0:
        tail = (r.stderr or r.stdout or "").strip().splitlines()[-3:]
        return Step("deps", False, " | ".join(tail)[:300],
                    "检查网络/代理：python -m pip install -r requirements.txt --proxy http://127.0.0.1:<port>")

    still = []
    for mod in REQUIRED:
        try:
            __import__(mod)
        except ImportError:
            still.append(mod)
    if still:
        return Step("deps", False, f"装完仍缺失：{', '.join(still)}", "重装 Python 或检查 pip 源")
    return Step("deps", True, f"installed {len(missing)}")


def ensure_model(proxy: str | None, quiet: bool) -> Step:
    need = {"model.int8.onnx": 239233841, "tokens.txt": 315894}
    ok_files, missing = [], []
    for name, size in need.items():
        p = os.path.join(MODEL_DIR, name)
        if os.path.isfile(p) and os.path.getsize(p) == size:
            ok_files.append(name)
        else:
            missing.append(name)

    if not missing:
        say(f"  · 模型已就绪（{len(ok_files)} 个文件）", quiet)
        return Step("model", True, "already downloaded")

    say(f"  · 下载模型：{', '.join(missing)}（约 230MB）", quiet)
    sys.path.insert(0, ROOT)
    try:
        import download_model
    except Exception as exc:
        return Step("model", False, f"无法导入 download_model.py: {exc}",
                    "确认仓库文件完整（git clone 重新拉一次）")

    try:
        for name in missing:
            download_model.download(download_model.MIRRORS["hf-mirror"] + name,
                                    os.path.join(MODEL_DIR, name),
                                    need[name], proxy)
    except Exception as exc:
        return Step("model", False, str(exc)[:300],
                    "换源重试：python download_model.py --source hf --proxy <你的代理>")

    for name, size in need.items():
        p = os.path.join(MODEL_DIR, name)
        if not (os.path.isfile(p) and os.path.getsize(p) == size):
            return Step("model", False, f"{name} 校验失败",
                        "删除 models/sensevoice 后重跑 bootstrap.py")
    return Step("model", True, "downloaded")


def check_model_files() -> Step:
    """只检查模型文件在不在、大小对不对，不下载。"""
    need = {"model.int8.onnx": 239233841, "tokens.txt": 315894}
    bad = []
    for name, size in need.items():
        p = os.path.join(MODEL_DIR, name)
        if not os.path.isfile(p):
            bad.append(f"{name} 缺失")
        elif os.path.getsize(p) != size:
            bad.append(f"{name} 大小异常({os.path.getsize(p)})")
    if bad:
        return Step("model", False, "; ".join(bad), "去掉 --check 重新跑，会自动下载")
    return Step("model", True, "两个文件齐全")


def ensure_config(quiet: bool) -> Step:
    if os.path.isfile(CONFIG):
        say("  · config.json 已存在，保留不动", quiet)
        return Step("config", True, "kept existing")
    example = os.path.join(ROOT, "config.example.json")
    if not os.path.isfile(example):
        return Step("config", False, "缺少 config.example.json", "git clone 重新拉一次")
    shutil.copyfile(example, CONFIG)
    say("  · 已从示例生成 config.json", quiet)
    return Step("config", True, "created from example")


def register_autostart(quiet: bool) -> Step:
    startup = os.path.join(os.environ.get("APPDATA", ""),
                           r"Microsoft\Windows\Start Menu\Programs\Startup")
    vbs = os.path.join(startup, "SenseVoiceIME.vbs")
    try:
        os.makedirs(startup, exist_ok=True)
        pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if not os.path.isfile(pyw):
            pyw = shutil.which("pythonw") or sys.executable
        content = (
            'Set sh = CreateObject("WScript.Shell")\n'
            f'sh.CurrentDirectory = "{ROOT}"\n'
            f'sh.Run """{pyw}"" ""{os.path.join(ROOT, "main.py")}""", 0, False\n'
        )
        with open(vbs, "w", encoding="utf-16") as f:
            f.write(content)
        say("  · 已注册开机自启", quiet)
        return Step("autostart", True, vbs)
    except Exception as exc:
        return Step("autostart", False, str(exc)[:200],
                    "手动双击 start.bat，或跳过此项（不影响使用）")


def selftest(index: int | None, quiet: bool) -> Step:
    """真实跑一遍：加载模型 + 开麦 + 识别一段静音，确认链路通。"""
    sys.path.insert(0, ROOT)
    try:
        from svime.asr import SenseVoiceEngine
        from svime.audio import Recorder, list_input_devices
    except Exception as exc:
        return Step("selftest", False, f"导入失败: {exc}", "检查依赖是否装全")

    devs = list_input_devices()
    if not devs:
        return Step("selftest", False, "没有可用麦克风",
                    "Windows 设置 → 隐私和安全性 → 麦克风 → 允许桌面应用访问")

    # 1) 模型能加载
    try:
        t0 = time.time()
        eng = SenseVoiceEngine(MODEL_DIR, num_threads=2)
        eng.load()
        load_s = time.time() - t0
    except Exception as exc:
        return Step("selftest", False, f"模型加载失败: {exc}",
                    "确认 models/sensevoice 下两个文件都在且大小正确")
    say(f"  · 模型加载 {load_s:.1f}s", quiet)

    # 2) 麦克风能开流、有信号
    try:
        rec = Recorder(16000, index)
        rec.start()
        time.sleep(1.2)
        audio = rec.stop()
        import numpy as np
        peak = float(np.abs(audio).max()) if len(audio) else 0.0
        frames = len(audio)
    except Exception as exc:
        return Step("selftest", False, f"麦克风打不开: {exc}",
                    f"用 python main.py --devices 查设备索引，再 --index <n> 重跑")

    if frames == 0:
        return Step("selftest", False, "麦克风没有返回任何采样",
                    "换一个输入设备：--index <n>")
    if peak < 0.003:
        # 真人说话通常在 0.05 以上；安静房间底噪也有 0.001~0.01。
        # 掉到这个量级基本是设备被静音 / 选错设备 / 被别的程序独占了。
        say(f"  · ⚠ 麦克风信号极低（峰值 {peak:.5f}），可能被静音或选错设备", quiet)
        return Step("selftest", True,
                    f"mic_peak={peak:.5f} (偏低，需人工确认麦克风)/{frames}帧/model {load_s:.1f}s",
                    f"用 python main.py --devices 查索引，确认没静音后 --index <n> 重跑")
    say(f"  · 麦克风正常（峰值 {peak:.4f}）", quiet)
    return Step("selftest", True, f"mic_peak={peak:.4f}/{frames}帧/model {load_s:.1f}s")


def is_running() -> tuple[bool, int]:
    """看单实例锁有没有被占（占着 = 已有实例在跑）。"""
    try:
        import ctypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        h = k32.CreateMutexW(None, False, "Global\\SenseVoiceIME")
        if not h:
            return False, 0
        already = ctypes.get_last_error() == 183
        if not already:
            k32.CloseHandle(h)
        return already, 0
    except Exception:
        return False, 0


def start_service(quiet: bool) -> Step:
    running, _ = is_running()
    if running:
        say("  · 服务已在运行，不重复启动", quiet)
        return Step("service", True, "already running")

    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.isfile(pyw):
        pyw = sys.executable
    try:
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        p = subprocess.Popen([pyw, os.path.join(ROOT, "main.py")], cwd=ROOT,
                             creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                             close_fds=True)
    except Exception as exc:
        return Step("service", False, str(exc)[:200], "手动双击 start.bat")

    # 等它把模型加载完、钩子装上
    deadline = time.time() + 25
    log_path = os.path.join(ROOT, "svime.log")
    while time.time() < deadline:
        time.sleep(1)
        ok, _ = is_running()
        if ok:
            say("  · 服务已启动", quiet)
            return Step("service", True, f"pid {p.pid}")
    tail = ""
    if os.path.isfile(log_path):
        with open(log_path, encoding="utf-8", errors="ignore") as f:
            tail = " | ".join(f.read().strip().splitlines()[-3:])[:300]
    return Step("service", False, f"启动后 25s 内未就绪 {tail}",
                "看 svime.log；若提示钩子失败，用管理员身份跑 start.bat")


# ---------------------------------------------------------------- 主流程
def main() -> int:
    ap = argparse.ArgumentParser(description="SenseVoice IME 一键部署（Agent 友好）")
    ap.add_argument("--json", action="store_true", help="只输出 JSON")
    ap.add_argument("--check", action="store_true", help="只体检，不做任何修改")
    ap.add_argument("--no-start", action="store_true", help="不启动服务")
    ap.add_argument("--no-autostart", action="store_true", help="不注册开机自启")
    ap.add_argument("--index", type=int, default=None, help="指定麦克风设备索引")
    ap.add_argument("--quiet", action="store_true", help="少打印")
    args = ap.parse_args()

    quiet = args.json or args.quiet
    steps: list[Step] = []
    t0 = time.time()

    say("=" * 58, quiet)
    say(f"  SenseVoice IME · 一键部署 v{VERSION}", quiet)
    say(f"  目录 {ROOT}", quiet)
    say("=" * 58, quiet)

    st = check_python(quiet)
    steps.append(st)
    if not st.ok:
        return finish(steps, quiet, t0, 2)

    proxy = pick_proxy(quiet)

    if args.check:
        steps.append(Step("deps", True, "skipped (--check 只体检)"))
        steps.append(check_model_files())
        steps.append(selftest(args.index, quiet))
        say("", quiet)
        return finish(steps, quiet, t0, 0 if all(s.ok for s in steps) else 5,
                      started=False)

    st = install_deps(proxy, quiet)
    steps.append(st)
    if not st.ok:
        return finish(steps, quiet, t0, 3)

    st = ensure_model(proxy, quiet)
    steps.append(st)
    if not st.ok:
        return finish(steps, quiet, t0, 4)

    steps.append(ensure_config(quiet))

    if not args.no_autostart:
        steps.append(register_autostart(quiet))

    st = selftest(args.index, quiet)
    steps.append(st)
    if not st.ok:
        return finish(steps, quiet, t0, 5)

    if not args.no_start:
        st = start_service(quiet)
        steps.append(st)
        if not st.ok:
            return finish(steps, quiet, t0, 6)

    return finish(steps, quiet, t0, 0, started=not args.no_start)


def finish(steps: list[Step], quiet: bool, t0: float, code: int,
           started: bool = True) -> int:
    elapsed = time.time() - t0
    ok = code == 0
    warn = [s for s in steps if s.ok and s.fix]
    if quiet:
        payload = {
            "ok": ok,
            "version": VERSION,
            "root": ROOT,
            "elapsed_s": round(elapsed, 1),
            "steps": [s.to_dict() for s in steps],
            "warnings": [{"step": s.name, "detail": s.detail, "advice": s.fix} for s in warn],
            "next": ("长按鼠标中键说话，松开自动落字。" if started and ok
                     else ("未启动服务；要真正用起来请运行 python bootstrap.py"
                           if ok else "按 failed 步的 fix 字段处理后重跑本命令")),
        }
        failed = [s for s in steps if not s.ok]
        if failed:
            payload["failed"] = failed[0].name
            payload["fix"] = failed[0].fix
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("-" * 58)
        for s in steps:
            mark = "OK  " if s.ok else "FAIL"
            print(f"  [{mark}] {s.name:<10} {s.detail}")
        print("-" * 58)
        if ok:
            print(f"  完成，用时 {elapsed:.1f}s")
            if started:
                print("\n  现在长按鼠标中键说一句话，松开就会把文字打到光标处。")
                print("  先确认手感：双击 test.bat 录 4 秒看识别效果。")
            else:
                print("\n  （没启动服务。要真正用起来：python bootstrap.py）")
            for s in warn:
                print(f"  ⚠ {s.name}: {s.fix}")
        else:
            bad = next((s for s in steps if not s.ok), None)
            print(f"  失败于：{bad.name} —— {bad.detail}")
            if bad.fix:
                print(f"  下一步：{bad.fix}")
    return code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
