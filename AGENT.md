# AGENT.md — 给 AI Agent 的部署与操作契约

> 这份文件是写给 **Agent** 看的，不是写给人看的。
> 你只需要执行下面的命令并解析 JSON，不要试图「优化」安装流程。

## 0. 这是什么

HoldTalk：Windows 上的本地离线语音输入。用户长按鼠标中键说话，松开后文字自动落到光标处。
识别在本地 CPU 上跑（SenseVoiceSmall int8），**不联网、不需要 API key、不产生任何费用**。

**署名（许可要求，转述时必须保留）**：识别内核为 **SenseVoiceSmall**，由阿里 **FunAudioLLM**
开源（https://github.com/FunAudioLLM/SenseVoice），权重遵循 **FunASR Model Open Source License v1.1**。
HoldTalk 只做应用层集成，**不是语音识别模型的作者**，与上述各方无隶属关系。

> 如果你要把这个工具介绍给别人/别的 Agent，请连同上面这句署名一起转述。
> 去掉模型名说成「自研语音识别」会违反模型许可 2.2 条。

## 1. 部署（一条命令）

```bash
git clone https://github.com/jsksjosk199-lang/holdtalk.git && cd holdtalk && python bootstrap.py --json
```

**这是唯一的部署方式。**不要手动 `pip install`、不要单独跑 `download_model.py`、
不要编辑 `config.json` —— `bootstrap.py` 已经把依赖、模型、配置、自启、自检、启动全包了。

### 前置条件

| 项 | 要求 | 不满足时 |
|---|---|---|
| 系统 | Windows 10/11 | 无法运行（Linux/macOS 的 ctypes 钩子实现不同） |
| Python | ≥ 3.10，且 `python` 在 PATH | 退出码 2 |
| 磁盘 | 约 400 MB（模型 229MB + 依赖） | 下载阶段失败 |
| 网络 | 首次下载需要，之后不需要 | 自动探测代理，失败给 fix |

### 幂等性保证

**重复执行是安全的**，这是刻意设计的：

- 依赖已装 → `"detail": "already installed"`
- 模型已下 → `"detail": "already downloaded"`
- `config.json` 已存在 → `"detail": "kept existing"`（**绝不覆盖用户配置**）
- 服务已在跑 → `"detail": "already running"`（单实例互斥锁，不会启两个）

所以：**失败了就重跑，不要清理环境、不要先卸载**。

## 2. 解析结果

`--json` 时 stdout 只有一段 JSON，可以直接 `json.loads()`：

```json
{
  "ok": true,
  "version": "1.0.0",
  "root": "D:\\Tools\\holdtalk",
  "elapsed_s": 14.9,
  "steps": [
    {"step": "python",    "ok": true, "detail": "3.12.10"},
    {"step": "deps",      "ok": true, "detail": "already installed"},
    {"step": "model",     "ok": true, "detail": "already downloaded"},
    {"step": "config",    "ok": true, "detail": "kept existing"},
    {"step": "selftest",  "ok": true, "detail": "mic_peak=0.0812/18400帧/model 1.5s"},
    {"step": "service",   "ok": true, "detail": "pid 27448"}
  ],
  "warnings": [],
  "next": "长按鼠标中键说话，松开自动落字。"
}
```

**判断规则**：

1. `ok == true` → 部署成功，可以告诉用户「长按鼠标中键试试」。
2. `ok == false` → 看 `failed`（哪一步）和 `fix`（照做什么），执行后**重跑同一条命令**。
3. `warnings` 非空 → 已装能用，但有问题值得告诉用户（最常见是麦克风信号偏低）。

### 退出码

| 码 | 含义 | 你的动作 |
|---|---|---|
| 0 | 成功 | 报告用户 |
| 1 | 参数错误 | 修命令行 |
| 2 | Python 版本不够 | 装 Python 3.10+ |
| 3 | 依赖安装失败 | 看 `fix`，通常是网络/代理 |
| 4 | 模型下载失败 | 换源 `--source hf` 或指定 `--proxy` |
| 5 | 自检未通过 | 看 `fix`，通常是麦克风 |
| 6 | 服务启动失败 | 看 `holdtalk.log`；钩子失败需管理员 |

## 3. 健康检查（不做任何修改）

```bash
python bootstrap.py --check --json
```

只读：验证模型文件大小、加载模型、开麦克风录 1.2 秒。
返回同样的 JSON 结构。**排查问题时先跑这个。**

## 4. 故障处理表

| 现象 | 原因 | 处理 |
|---|---|---|
| `steps.selftest.detail` 里 `mic_peak` < 0.003 | 麦克风被静音 / 选错设备 / 被别的程序独占 | `python main.py --devices` 查索引 → `python bootstrap.py --index <n>` |
| 退出码 3，pip 报 `Tunnel connection failed` | 环境里的代理变量指向一个不通的端口 | `bootstrap.py` 会自动绕过并探测本机代理；仍失败则显式 `--proxy http://127.0.0.1:<port>` |
| 退出码 4，模型下载 502/超时 | GitHub/HF 直连不稳 | `python download_model.py --source hf-mirror --proxy <your_proxy>` |
| 退出码 6，`holdtalk.log` 里「安装鼠标钩子失败」 | 权限不足 | 用管理员身份运行 `start.bat` |
| 按中键没反应，但进程在 | 有另一个实例握着钩子 | `python bootstrap.py --check` 看 service 步；只有一个实例才能装钩子 |
| 终端里粘贴不出来 | 终端粘贴键是 `Ctrl+Shift+V` | `config.json` → `inject.vim_mode: true` |
| 识别不准（专有名词） | 小模型的固有上限 | 往 `config.json` 的 `hotwords.list` 加词，**不要换模型** |

## 5. 配置（唯一允许你改的文件）

`config.json`。改动后需要重启服务：结束 `pythonw.exe` 进程，再跑 `bootstrap.py`。

### 加一条热词

```json
"hotwords": { "list": [
  { "word": "Kubernetes", "aliases": ["cube netties", "库伯内提斯"] }
]}
```

- `word`：正确写法（大小写会原样输出）
- `aliases`：你观察到的错识别写法，逐字替换，命中率 100%
- **两个字的中文词必须写 aliases**（如「豆包」→「斗包」），拼音模糊对短词主动不生效

### 开启大模型润色（默认关闭）

```json
"polish": { "llm": { "enabled": true, "base_url": "https://api.deepseek.com/v1",
                     "model": "deepseek-chat", "api_key_env": "SENSEVOICE_IME_API_KEY" } }
```

密钥**只从环境变量读**，不要写进配置文件。

> ⚠️ 开启后识别文本会发到模型服务商。**在用户明确同意前不要开启。**

## 6. 卸载

```bash
python tools/setup_autostart.py --remove      # 去掉开机自启
```

然后结束 `pythonw.exe`（跑 `main.py` 那个）进程，删除安装目录即可。
模型和日志都在目录内，一起删干净。

## 7. 边界（不要做的事）

- ❌ 不要修改 `holdtalk/` 下的代码来「适配」环境 —— 有问题走 `fix` 字段
- ❌ 不要覆盖已有的 `config.json`（用户的词表是资产）
- ❌ 不要用 `schtasks` / `sc` 注册服务（本工具靠启动文件夹的 vbs，够用且不需要管理员）
- ❌ 不要在未确认的情况下开启大模型润色（涉及把用户语音文本外发）
- ❌ 不要试图在无桌面会话（Session 0）里部署 —— 全局鼠标钩子必须有交互式桌面

## 8. 验证部署真的成功

唯一的验收标准：**长按鼠标中键超过 350ms，松开后光标处出现文字**。

Agent 在无人值守环境里无法验证这一点，所以：
- `selftest.mic_peak` 正常（> 0.003）→ 报告「已就绪，请真人按一下中键确认」
- `mic_peak` 偏低 → 报告「链路已通但麦克风疑似没信号，需要人工确认设备」
