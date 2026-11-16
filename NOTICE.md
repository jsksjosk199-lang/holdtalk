# NOTICE — 第三方组件与许可

本项目（SenseVoice IME）的**自有代码**采用 MIT 许可证，见 [LICENSE](LICENSE)。

本项目的**语音识别能力来自第三方开源项目**，不是本项目原创。以下是完整清单与各自的许可状态。

## 1. 识别模型：SenseVoiceSmall

| 项 | 内容 |
|---|---|
| 项目 | SenseVoice / SenseVoiceSmall |
| 维护方 | 阿里 FunAudioLLM（现迁至 QwenAudio 组织） |
| 上游地址 | https://github.com/FunAudioLLM/SenseVoice |
| **仓库源码许可** | **MIT** |
| **模型权重许可** | **FunASR Model Open Source License Agreement v1.1** |
| 商用 | **允许**。官方已澄清：Section 3 是责任与风险免责条款，不是额外的非商用限制 |

官方澄清中有两条**仍然适用**，使用方需自行遵守：

1. **署名要求（Section 2.2）**：需保留对模型来源的署名；
2. **模型名称要求（Section 2.2）**：不得以官方名义误导用户。

> 本仓库**不分发模型权重**。`models/` 已列入 `.gitignore`，模型由 `download_model.py`
> 从第三方仓库按需下载。这样做是为了避免构成「权重再分发」，把许可义务留给最终使用者自行判断。

## 2. 模型转换版（实际下载的那个文件）

本项目下载的是 sherpa-onnx 社区转换的 ONNX 量化版本：

- 地址：`https://huggingface.co/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17`
- 转换自：FunAudioLLM/SenseVoice
- **该仓库未声明独立许可证**（model card 的 YAML 元数据为空，正文仅说明「转换自 SenseVoice」）

⚠️ **这是一个许可链条上的不确定点。** 上游官方说明明确提到：
「本澄清仅覆盖官方权重，第三方转换版本请单独核对其条款。」

如果你要在商业场景中依赖这个 ONNX 转换版，建议：
- 直接用官方权重自行转换（转换工具在 sherpa-onnx 仓库里），许可路径更清晰；
- 或联系转换作者 `csukuangfj` 确认授权。

## 3. 运行时与依赖

| 组件 | 用途 | 许可 | 商用 |
|---|---|---|---|
| [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) | ONNX 推理运行时 | Apache-2.0 | ✅ |
| [pypinyin](https://github.com/mozillazg/python-pinyin) | 汉字转拼音（热词模糊匹配） | MIT | ✅ |
| [sounddevice](https://github.com/spatialaudio/python-sounddevice) | 麦克风录音 | MIT | ✅ |
| [numpy](https://numpy.org/) | 音频数组运算 | BSD-3-Clause | ✅ |

以上全部是宽松许可证，允许商用、闭源、修改，只需保留版权与许可声明。

## 4. 本项目原创的部分

以下代码为本项目原创（MIT，可自由使用）：

- `svime/hook.py` —— 低级鼠标钩子 + 长按判定 + 单实例锁
- `svime/audio.py` —— 录音、静音裁剪、线性重采样
- `svime/hotwords.py` —— 别名精确替换 + 拼音音节编辑距离模糊匹配 + 冲突消解
- `svime/polish.py` —— 本地填充词清理规则 + 大模型润色可插拔层
- `svime/inject.py` —— 剪贴板/Unicode 双通道文本注入
- `svime/asr.py`、`svime/app.py`、`bootstrap.py` —— 引擎封装、流程编排、一键部署

## 5. 非官方声明

**本项目是第三方独立项目，与阿里 FunAudioLLM、QwenAudio、k2-fsa（sherpa-onnx 维护方）
均无隶属或背书关系。** 项目名中的 "SenseVoice" 仅用于说明所用识别内核，不代表官方实现。

如果你希望**彻底避免名称混淆**，可自行把项目重命名（例如 `sv-ime`、`hold-to-talk`），
并在 README 中改为「识别内核使用 SenseVoiceSmall」这样的表述——功能不受影响。
