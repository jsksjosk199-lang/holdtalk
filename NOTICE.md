# NOTICE — 第三方组件、许可与署名

本项目 **HoldTalk** 的自有代码采用 MIT 许可证，见 [LICENSE](LICENSE)。

**语音识别能力不是本项目原创**，来自第三方开源模型。以下是完整清单、许可状态，
以及本项目为满足许可要求所做的具体动作。

---

## 1. 识别模型：SenseVoiceSmall

| 项 | 内容 |
|---|---|
| 模型名 | **SenseVoiceSmall** |
| 作者 | 阿里 **FunAudioLLM** 团队 |
| 上游仓库 | https://github.com/FunAudioLLM/SenseVoice（现由 QwenAudio 组织维护） |
| 仓库源码许可 | MIT |
| **权重许可** | **FunASR Model Open Source License Agreement v1.1** |
| 全文 | https://github.com/modelscope/FunASR/blob/main/MODEL_LICENSE |

### 商用是否允许

**允许。** 该协议 2.1 条写明「You are free to use, copy, modify, and share」。
上游维护方另有一份澄清：协议第 3 条是**责任与风险免责**，不是额外的非商用限制。

### 本项目必须履行的义务（协议 2.2 条）

原文：

> When using, copying, modifying, and sharing [FunASR Software], you must **attribute the source
> and author information** and **retain relevant model names** in [FunASR Software].

即两项：

1. **标注来源与作者** → 本项目在 README 顶部设「识别内核署名」区块，本文件列明作者与仓库地址；
2. **保留模型名称** → 项目已更名为 `HoldTalk`，但 `SenseVoice` / `SenseVoiceSmall` 这一**模型名称在所有文档中完整保留**，
   不做任何抹除或改写。

> 2.2 条约束的是「不要抹掉模型名冒充自研」，**不禁止**给应用层起自己的名字。
> 本项目因此采用「应用名 HoldTalk + 显式署名 SenseVoiceSmall」的组合。

---

## 2. 实际下载的模型文件

本项目下载的是 sherpa-onnx 社区转换的 ONNX 量化版：

- 地址：`https://huggingface.co/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17`
- 转换自：FunAudioLLM/SenseVoice
- **该仓库根目录有 `LICENSE` 文件，正文为**：

  ```
  Ref to https://github.com/modelscope/FunASR?tab=readme-ov-file#license
  ```

即转换版**明确把许可指回 FunASR**，与官方权重同一套条款。许可链条是闭合的，不存在「无许可」的缺口。

仓库内还附带 `export-onnx.py`（转换脚本），可自行复现转换过程。

---

## 3. 本项目不分发模型权重

`models/` 已列入 `.gitignore`，模型由 `download_model.py` 从上述第三方仓库按需下载。

这样做的原因：避免构成「权重再分发」，让最终使用者直接与上游许可建立关系，不经过本项目转手。

---

## 4. 运行时与依赖

| 组件 | 用途 | 许可 | 商用 |
|---|---|---|---|
| [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) | ONNX 推理运行时 | Apache-2.0 | ✅ |
| [pypinyin](https://github.com/mozillazg/python-pinyin) | 汉字转拼音（热词模糊匹配） | MIT | ✅ |
| [sounddevice](https://github.com/spatialaudio/python-sounddevice) | 麦克风录音 | MIT | ✅ |
| [numpy](https://numpy.org/) | 音频数组运算 | BSD-3-Clause | ✅ |

以上均为宽松许可，允许商用、闭源、修改，仅需保留版权与许可声明。

---

## 5. 本项目原创的部分（MIT）

- `holdtalk/hook.py` —— 低级鼠标钩子 + 长按判定 + 单实例互斥锁
- `holdtalk/audio.py` —— 录音、静音裁剪、线性重采样
- `holdtalk/hotwords.py` —— 别名精确替换 + 拼音音节编辑距离模糊匹配 + 冲突消解
- `holdtalk/polish.py` —— 本地填充词清理规则 + 可插拔大模型润色层
- `holdtalk/inject.py` —— 剪贴板 / Unicode 双通道文本注入
- `holdtalk/asr.py`、`holdtalk/app.py` —— 引擎封装与流程编排
- `bootstrap.py` —— 幂等一键部署
- `AGENT.md`、`README.md` —— 文档

---

## 6. 隐私说明

- **音频不落盘**：录音只存在于进程内存（numpy 数组），识别完立即丢弃，不写任何音频文件；
- **不出网**：识别全程本地 CPU，不发起网络请求；
- **大模型润色默认关闭**：`polish.llm.enabled` 默认 `false`。一旦开启，**识别出的文字会发送到
  你自己配置的模型服务商**——这是唯一的外发路径，由使用者自主决定；
- **剪贴板**：`inject.method=clipboard` 会临时写入剪贴板并在粘贴后还原原内容；
  若不想碰剪贴板，可改为 `"method": "typing"`（逐字符注入）。

---

## 7. 非官方声明

**HoldTalk 是第三方独立项目，与阿里巴巴集团、FunAudioLLM、QwenAudio、k2-fsa（sherpa-onnx 维护方）
均无隶属、合作或背书关系。** 本项目不对上述任何一方主张任何权利。

文档中提到上述名称，仅为**如实标注技术来源**，属于许可要求的署名行为，不构成任何形式的官方授权暗示。
