<div align="center">

<img src="https://raw.githubusercontent.com/ErisPulse/ErisPulse/main/.github/assets/ErisPulseLogo.png" width="180" alt="ErisPulse-TTS" />

<img src="https://raw.githubusercontent.com/ErisPulse/.github/main/assets/badges/module.svg" alt="ErisPulse Module" />

</div>

# ErisPulse-TTS

**给 ErisPulse 生态用的通用语音合成模块：接任意 OpenAI 兼容 `/audio/speech` 接口，默认 SiliconFlow CosyVoice2。合成、发语音、克隆音色，装上一个模块就多一种"说话"的能力。**

语音这件事本来不该绑死在某个厂商身上。SiliconFlow 的 TTS 端点与 OpenAI 的 `/audio/speech` 同构——同样的 `model` / `input` / `voice` / `response_format` 参数——所以模块只实现一套协议：换 `provider` 和 `base_url` 就换供应商，`model` 和 `voice` 决定听起来是谁。默认配置直接指向 SiliconFlow 的 `FunAudioLLM/CosyVoice2-0.5B`，开箱即用。

模块本身不做"什么时候该说话"的判断。它把能力交给生态：`tts_speak`、`tts_synthesize` 等六个服务经 QvQChat 的生态桥变成 AI 工具，再通过 `qvq_extensions` 注入一条使用建议——短句口语适合语音，代码、表格、长文和任务结果保持文字。由模型自己决定调用与否，模块只负责把文字变成声音、把声音送到会话。装它不需要改 QvQChat，卸它也不会留下任何钩子。

<p>

  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10+-FFD43B?style=for-the-badge&logo=python&logoColor=blue" alt="Python"></a>

  <a href="https://github.com/ErisPulse/ErisPulse"><img src="https://img.shields.io/badge/ErisPulse-2.8.0+-00A3FF?style=for-the-badge" alt="ErisPulse"></a>

  <a href="./LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge" alt="License"></a>

</p>

---

## 安装

需要 ErisPulse 2.8.0 或更高版本，以及一个支持 `Voice` 发送方法的适配器（OneBot 系适配器均支持）。

```bash
pip install ErisPulse-TTS
# 或本地开发
pip install -e .
```

## 配置

配置项出现在框架配置的 `[TTS]` 段，装了 QvQChat 时也会出现在其 Dashboard 设置页的插件分区：

```toml
[TTS]
provider = "siliconflow"          # siliconflow / openai / custom
base_url = ""                     # 留空用预设；provider=custom 时必填
api_key = "sk-..."                # 硅基流动：cloud.siliconflow.cn/account/ak
model = "FunAudioLLM/CosyVoice2-0.5B"
default_voice = "FunAudioLLM/CosyVoice2-0.5B:alex"
response_format = "mp3"           # mp3 / wav / pcm / opus
sample_rate = 44100
speed = 1.0                       # 0.25 - 4.0
gain = 0.0                        # -10 - 10 dB（硅基流动）
max_chars = 500                   # 超长按句切分
max_segments = 3
cache_enabled = true              # 文本+音色+参数 哈希缓存，不重复计费
cache_dir = "data/TTS/audio"
send_method = "Voice"             # 部分平台用 Record
```

系统预置 8 种音色，使用时必须带模型前缀：

| 男声 | alex 沉稳 / benjamin 低沉 / charles 磁性 / david 欢快 |
|---|---|
| 女声 | anna 沉稳 / bella 激情 / claire 温柔 / diana 欢快 |

例如 `FunAudioLLM/CosyVoice2-0.5B:claire`。

## 服务

| 服务 | 说明 | 级别 |
|---|---|---|
| `tts_speak(text, platform, target_id, target_type="group", voice="", speed=0, emotion="")` | 合成并直接发送语音到指定会话 | safe |
| `tts_synthesize(text, voice="", speed=0, emotion="")` | 只合成，返回本地音频路径（可交给 `send_message` 的 `audio_path`） | safe |
| `tts_voices()` | 系统预设 + 已上传的克隆音色 | safe |
| `tts_clone(name, audio, text, model="")` | 上传参考音频创建音色，返回 `uri`（需服务商实名认证） | admin |
| `tts_delete_voice(uri)` | 删除克隆音色 | admin |
| `tts_status()` | 运行状态、默认音色与缓存统计 | safe |

`audio` 支持 http(s) URL、本地文件路径或 base64。参考音频建议 8–10 秒、单人、吐字清晰、无背景噪音、无房间回声。

## CosyVoice 的两个额外能力

**情感控制**：传 `emotion="高兴"` 时，输入会被包装成 `用高兴的情感说<|endofprompt|>正文`。模板由 `emotion_template` 控制，留空即关闭；其他提供方会自动忽略这个参数。

**动态音色（零样本克隆，不落库）**：把 `default_voice` 留空，配置一份参考音频：

```toml
reference_audio = "https://example.com/ref.mp3"
reference_text  = "参考音频里说的原文"
```

请求会带上 `references: [{"audio": ..., "text": ...}]`，用参考音频即时克隆，不必先上传建库。

## 与 QvQChat 配合

装上本模块后，QvQChat 的生态桥会自动注册 `eco_TTS_tts_speak` 等工具，并在系统提示里列出可用的生态能力：

- `qvq_schemas` 给每个参数配上说明，模型知道 `text`/`voice` 该写什么
- `qvq_access` 自声明 `tts_speak` / `tts_synthesize` / `tts_voices` 对普通成员开放，克隆与删除保持管理员
- `qvq_extensions` 注入一条使用建议，让 AI 自己判断何时该发语音、何时保持文字

QvQChat 侧没有任何 TTS 专属配置或代码路径——这是刻意的：主模块不认识任何具体生态模块，能力全靠约定服务注入。

## 缓存与长文本

同一段文本（同一音色、语速、情感、格式）在 `cache_dir` 里只落一次文件，重复请求直接复用，不再触发计费。缓存文件超过 `cache_max_files` 时按修改时间淘汰最旧。

超过 `max_chars` 的文本按句末标点切分，最多 `max_segments` 段；超出段数的部分合并进最后一段。每段单独合成、依次发送。

## 开发

```bash
pip install -e ".[test]"
python -m pytest tests/ -q
```

## 许可证

MIT
