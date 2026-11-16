# HoldTalk

> 长按鼠标中键说话，松开就落字。**全程本地离线**，不联网、不上传、不花钱。

> **给 AI Agent**：一条命令部署，契约见 **[AGENT.md](AGENT.md)**。
> ```bash
> git clone https://github.com/jsksjosk199-lang/holdtalk.git && cd holdtalk && python bootstrap.py --json
> ```
> 幂等、非交互、输出 JSON + 退出码，失败自带 `fix` 字段。重跑安全，不会覆盖已有配置。

一个 Windows 上的语音输入小工具：按住鼠标中键 → 说话 → 松开，识别出的文字直接出现在你当前光标处。

短按中键仍然是原来的中键功能（浏览器新标签、CAD 平移……一个都不少）。

```
按住中键 350ms  →  嘟（开始录音）
说话 …
松开           →  嘟（停止）→ 识别 → 热词 → 润色 → 自动粘贴到光标处
```

---

## 识别内核署名（重要）

**本项目的语音识别能力不是自研的。** 它来自阿里 **FunAudioLLM** 团队开源的 **SenseVoiceSmall** 模型：

| 项 | 内容 |
|---|---|
| 模型 | **SenseVoiceSmall** |
| 作者 / 来源 | 阿里 **FunAudioLLM**（上游仓库 [QwenAudio/SenseVoice](https://github.com/FunAudioLLM/SenseVoice)） |
| 权重许可 | [FunASR Model Open Source License Agreement v1.1](https://github.com/modelscope/FunASR/blob/main/MODEL_LICENSE) |
| 推理运行时 | [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)（Apache-2.0） |

本项目做的是**应用层集成**：鼠标钩子触发、录音、热词纠错、文本润色、光标注入、一键部署。
项目名 `HoldTalk` 是应用名，**不代表对模型的任何主张**；模型名称 `SenseVoice` 予以保留并在此署名，
以符合上述许可 **2.2 条「须标注来源与作者信息、保留相关模型名称」** 的要求。

详细许可清单与商用条件见 **[NOTICE.md](NOTICE.md)**。

---

## 为什么不用 Win+H

Windows 自带的语音听写（`Win+H`）能用，但有三个硬伤：

| 问题 | `Win+H` | 本项目 |
|---|---|---|
| **热词** | 不能自定义。`WorkBuddy` 会给你写成 `work body` | 一张可编辑的热词表，别名 + 拼音模糊双保险 |
| **口水词** | 原样保留，「嗯、那个、就是说」全留着 | 本地规则先削一遍，可选再过大模型理顺 |
| **网络** | 走 Azure 在线识别，断网即废 | 完全本地，飞机上也能用 |
| **触发** | 得按 `Win+H`，手要离开鼠标 | 鼠标中键长按，手不离鼠标 |

第一条是最要命的。实测原句：

```
识别原始：  嗯，那个我今天想跟你讲一下，就是说work body这个工具其实挺好用的。然后我们再看看千问和豆包。
本工具输出：我今天想跟你讲一下，WorkBuddy这个工具其实挺好用的。然后我们再看看千问和豆包。
```

`work body` → `WorkBuddy`，「嗯、那个、就是说」被削掉，句子还是你原本的语气。

---

## 特性

- **完全离线**：模型在本地跑，音频不出机器，不调用任何云服务
- **纯 CPU**：不需要显卡、不需要 PyTorch，229MB 的 int8 量化模型，常驻约 386MB 内存
- **快**：10.86 秒音频识别耗时 1.38 秒（RTF ≈ 0.13，约 7.6 倍实时），启动预热 2 秒
- **热词双层纠错**：别名精确替换（100% 可控）+ 拼音音节编辑距离模糊匹配（治同音错字）
- **两段式润色**：本地规则零延迟去口水词；大模型润色可插拔、默认关闭、密钥只读环境变量
- **不抢中键**：短按原样透传，逻辑里没有任何 `sleep` 阻塞鼠标钩子
- **单实例保护**：多开会被互斥量挡住，避免一条录音被处理两遍
- **零配置可跑**：装完依赖、下完模型，直接 `start.bat`

---

## 快速开始

**前提**：Windows 10/11 + Python 3.10 以上（安装时勾选 `Add python.exe to PATH`）。

```bat
git clone https://github.com/jsksjosk199-lang/holdtalk.git
cd holdtalk
install.bat
```

`install.bat` 会依次做三件事：装依赖 → 下载模型（约 230MB）→ 列出你的麦克风。

然后：

```bat
start.bat     :: 后台运行（无黑框），长按中键开用
test.bat      :: 录 4 秒，直接看识别效果（先跑这个确认麦克风正常）
```

想开机自启：

```bat
python tools\setup_autostart.py
```

卸载自启：`python tools\setup_autostart.py --remove`

---

## 配置（`config.json`）

### 热词表

这是整个工具最值钱的部分，值得花十分钟调。写法：

```json
"hotwords": {
  "enabled": true,
  "fuzzy": true,
  "list": [
    { "word": "WorkBuddy", "aliases": ["work body", "我的body", "沃克巴迪"] },
    { "word": "图吧工具箱", "aliases": ["图八工具箱"] },
    { "word": "豆包", "aliases": ["斗包", "豆宝"] }
  ]
}
```

两层纠错各管一段：

- **别名（`aliases`）**：你写死的错法，逐字替换，不受任何阈值影响。
  **两个字的短词（豆包、千问）必须靠这个**，拼音模糊对短词误伤率太高，代码里主动排除了。
- **模糊匹配**：三个字以上的词才启用。中文走**拼音音节编辑距离**（`图八工具箱` → `图吧工具箱`，
  因为 `ba` == `ba` 而命中），英文走**字母相似度**（`cloud code` → `Claude Code`，
  `Work Buddy` → `WorkBuddy`）。

> 拼音模糊只允许极小误差（音节数 ≥ 3 时最多差 1 个音节），宁可漏纠也不错改。

### 润色

```json
"polish": {
  "local_rules": true,
  "llm": {
    "enabled": false,
    "base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",
    "api_key_env": "SENSEVOICE_IME_API_KEY"
  }
}
```

- `local_rules`：本地去口水词，**建议一直开着**，零成本零延迟。
- `llm`：默认关闭。开启后，识别结果会再发一次大模型做顺句。
  接口是 OpenAI 兼容格式，DeepSeek / 通义 / 智谱 / 本地 Ollama 都能接。
  **密钥只从环境变量读**（默认 `SENSEVOICE_IME_API_KEY`），不写进配置文件，不会被提交进仓库。

  ```bat
  setx SENSEVOICE_IME_API_KEY "your-key"
  ```

  本地 Ollama 连 key 都不用（`base_url` 指向 `http://127.0.0.1:11434/v1` 即可）。

  > 注意：开启大模型润色意味着**识别文本会发到你的模型服务商**。
  > 在意隐私就别开，本地规则已经能削掉大部分口水词。

### 其他常用项

| 配置 | 默认 | 说明 |
|---|---|---|
| `trigger.long_press_ms` | `350` | 长按阈值。调到 200 太容易误触，别再往下调 |
| `trigger.min_speech_ms` | `250` | 短于这个时长当误触丢掉 |
| `trigger.max_record_seconds` | `60` | 超长自动收尾 |
| `trigger.beep` | `true` | 开始/结束各响一声 |
| `audio.device` | `null` | 填 `python main.py --devices` 里的索引，可固定麦克风 |
| `inject.method` | `clipboard` | `clipboard`（快）或 `typing`（不碰剪贴板） |
| `inject.vim_mode` | `false` | 在终端里粘贴请开这个（终端要 `Ctrl+Shift+V`） |

---

## 工作原理

```
鼠标中键(低级钩子 WH_MOUSE_LL)
   │
   ├─ 短按 <350ms ──→ 原样发一次中键点击（透传）
   │
   └─ 长按 ≥350ms ──→ sounddevice 录音 16kHz
                        │
                     松开 → 能量裁剪静音
                        │
                     SenseVoice int8 (ONNX, CPU)
                        │
                     热词纠错（别名 → 拼音模糊）
                        │
                     本地润色（去填充词/压重复/整理标点）
                        │
                     [可选] 大模型理顺
                        │
                     剪贴板 + Ctrl+V 回填光标
```

几个刻意的设计选择：

- **钩子回调里绝不阻塞**。低级鼠标钩子有 300ms 超时线，超了会被系统摘掉。
  长按判定交给独立 `Timer`，短按透传直接发事件不 `sleep`。
  （上一版在钩子里 `sleep(0.05)`，结果每次短按中键整个系统的鼠标都顿 50ms。）
- **不用 `Win+H`**。那条路依赖系统听写，热词不可控、必须联网，是死路。
- **录音按需开流**。不常驻占用麦克风，避免和会议软件抢设备。
- **润色失败不丢原文**。大模型超时/报错/返回空，直接退回识别原文。

---

## 常见问题

**长按没反应？**
先看 `holdtalk.log`。如果钩子没装上，八成是权限问题——用管理员身份跑一次 `start.bat`。
另外确认没有第二个实例在跑（单实例锁会挡住第二个）。

**录不到声音？**
跑 `test.bat`，如果结果是空的或全是标点：
1. `python main.py --devices`，把正确的麦克风索引填进 `config.json` 的 `audio.device`；
2. 检查 Windows「设置 → 隐私和安全性 → 麦克风」是否允许桌面应用访问；
3. 笔记本留意有没有物理麦克风静音键（F 区那个）。

**在终端里粘贴不出来？**
把 `inject.vim_mode` 改成 `true`（终端里粘贴是 `Ctrl+Shift+V`，不是 `Ctrl+V`）。

**识别不准？**
这是 229MB 的小模型，不是千亿参数的大模型。它的强项是**响应快、能离线、听得清普通话**。
遇到专有名词就去加一条热词，比换模型有效得多。

**能识别英文吗？**
可以。这个模型本身支持中/英/日/韩/粤，会自动判断语种。中英混杂也能处理。

---

## 自测数据（本机实测，供参考）

| 项目 | 数值 |
|---|---|
| 模型体积 | 229 MB（`model.int8.onnx`） |
| 模型加载 | 2.0 ~ 3.0 s |
| 常驻内存 | 386 MB（含 Python 运行时） |
| 识别速度 | 空闲时 10.86s 音频 → 1.38s（RTF 0.13）；系统有别的高负载时同段音频实测到 4.9s |
| 测试环境 | Windows 11 / Intel Iris Xe 集显 / 纯 CPU / 2 线程 |

> 上面那组「原句 → 输出」的例子是用系统 TTS 合成的语音测的，属于冒烟测试。
> **真人的口音、语速、距离麦克风远近差异很大**，请务必自己用 `test.bat` 试一听。

---

## 目录结构

```
holdtalk/
├── bootstrap.py            一键部署（幂等 / 非交互 / JSON，Agent 用这个）
├── AGENT.md                给 AI Agent 的部署与操作契约
├── main.py                 入口（服务 / --test / --devices / --file）
├── download_model.py       模型下载（支持代理和镜像）
├── install.bat             双击安装（内部就是调 bootstrap.py）
├── start.bat               后台启动
├── test.bat                录 4 秒试听
├── config.json             你的配置（含热词表）
├── NOTICE.md               第三方组件与许可清单
├── holdtalk/
│   ├── asr.py              SenseVoice 引擎封装
│   ├── audio.py            录音与重采样
│   ├── hotwords.py         热词纠错（别名 + 拼音模糊）
│   ├── polish.py           本地润色 + 大模型润色
│   ├── inject.py           剪贴板/Unicode 注入
│   ├── hook.py             鼠标钩子 + 单实例锁
│   ├── app.py              主流程编排
│   └── config.py           配置合并
├── tools/
│   ├── bench_asr.py        识别速度自测
│   ├── make_test_wav.py    用系统 TTS 造测试音频
│   └── setup_autostart.py  开机自启
└── models/sensevoice/      模型文件（不提交，由脚本下载）
```

---

## 依赖与许可

本项目**自有代码**为 MIT（见 [LICENSE](LICENSE)）。完整许可清单与合规动作见 **[NOTICE.md](NOTICE.md)**。

| 组件 | 许可 | 商用 |
|---|---|---|
| 本项目代码（HoldTalk） | MIT | ✅ |
| [SenseVoiceSmall](https://github.com/FunAudioLLM/SenseVoice) 模型 | 代码 MIT / 权重 **FunASR Model License v1.1** | ✅ 允许，须署名并保留模型名 |
| [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)（推理运行时） | Apache-2.0 | ✅ |
| [pypinyin](https://github.com/mozillazg/python-pinyin) | MIT | ✅ |
| [sounddevice](https://github.com/spatialaudio/python-sounddevice) | MIT | ✅ |
| [numpy](https://numpy.org/) | BSD-3-Clause | ✅ |

**关于模型许可**（已核实，非推测）：

- SenseVoice 上游**代码是 MIT，权重是 FunASR Model Open Source License v1.1**；
- 该协议 **2.1 允许自由使用、修改、分享（含商用）**，第 3 条是责任免责而非非商用限制；
- **2.2 条要求**：标注来源与作者、**保留模型名称** —— 本项目通过在 README 署名区块与本文件履行；
- 本项目下载的 ONNX 转换版，其仓库根目录的 `LICENSE` 明确写「Ref to FunASR license」，
  **许可链条闭合**，与官方权重同一套条款；
- 本仓库**不分发模型权重**（`models/` 在 `.gitignore`，靠脚本下载），避免构成权重再分发。

**非官方声明**：HoldTalk 与阿里巴巴集团、FunAudioLLM、QwenAudio、k2-fsa 均无隶属或背书关系。
文档中出现这些名称，仅为许可要求的**技术来源署名**。
