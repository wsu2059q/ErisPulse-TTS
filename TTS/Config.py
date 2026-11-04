from __future__ import annotations

from dataclasses import dataclass, field
from dataclasses import fields as dc_fields

from ErisPulse.Core.Bases import BaseConfig

GROUP_META: dict[str, dict] = {
    "provider": {"order": 1},
    "voice": {"order": 2},
    "output": {"order": 3},
    "cache": {"order": 4},
}


def _desc(key: str, text: str, group: str, order: int, widget: str = "text",
          options: list | None = None, minimum: float | None = None,
          maximum: float | None = None, step: float | None = None,
          placeholder: str = "", secret: bool = False, dangerous: bool = False) -> dict:
    ui: dict = {"widget": widget, "group": group, "order": order}
    if options is not None:
        ui["options"] = options
    if minimum is not None:
        ui["min"] = minimum
    if maximum is not None:
        ui["max"] = maximum
    if step is not None:
        ui["step"] = step
    if placeholder:
        ui["placeholder"] = placeholder
    if secret:
        ui["secret"] = True
    if dangerous:
        ui["dangerous"] = True
    return {"description": {"i18n": f"TTS.{key}", "default": text}, "ui": ui}


@dataclass
class TTSConfig(BaseConfig):
    # ===== 提供方（OpenAI 兼容 /v1/audio/speech）=====
    provider: str = field(default="siliconflow", metadata=_desc(
        "provider", "提供方预设：siliconflow（默认，CosyVoice2）/ openai / custom（自填 base_url）",
        "provider", 1, "select", ["siliconflow", "openai", "custom"]))
    base_url: str = field(default="", metadata=_desc(
        "base_url", "接口 Base URL，留空使用预设（siliconflow: https://api.siliconflow.cn/v1 / openai: https://api.openai.com/v1）",
        "provider", 2, "text", placeholder="https://api.siliconflow.cn/v1"))
    api_key: str = field(default="", metadata=_desc(
        "api_key", "API Key（硅基流动在 cloud.siliconflow.cn/account/ak 获取）",
        "provider", 3, "text", secret=True))
    timeout: int = field(default=60, metadata=_desc(
        "timeout", "单次合成请求超时（秒）", "provider", 4, "number"))

    # ===== 模型与音色 =====
    model: str = field(default="FunAudioLLM/CosyVoice2-0.5B", metadata=_desc(
        "model", "TTS 模型名（siliconflow 常用 FunAudioLLM/CosyVoice2-0.5B、fnlp/MOSS-TTSD-v0.5）",
        "voice", 1, "text"))
    default_voice: str = field(default="FunAudioLLM/CosyVoice2-0.5B:alex", metadata=_desc(
        "default_voice", "默认音色。系统预设需带模型前缀（如 FunAudioLLM/CosyVoice2-0.5B:alex）；克隆音色填返回的 uri；留空表示使用下方参考音频动态音色",
        "voice", 2, "text"))
    speed: float = field(default=1.0, metadata=_desc(
        "speed", "语速（0.25-4.0）", "voice", 3, "slider", minimum=0.25, maximum=4.0, step=0.05))
    gain: float = field(default=0.0, metadata=_desc(
        "gain", "音量增益 dB（-10 到 10，仅硅基流动支持）", "voice", 4, "slider", minimum=-10, maximum=10, step=0.5))
    emotion_template: str = field(default="用{emotion}的情感说", metadata=_desc(
        "emotion_template", "情感控制前缀模板（CosyVoice 用 <|endofprompt|> 分隔指令与正文）；留空关闭情感控制",
        "voice", 5, "text"))
    reference_audio: str = field(default="", metadata=_desc(
        "reference_audio", "动态音色参考音频（URL / 本地路径 / base64）。default_voice 留空时用它做零样本克隆",
        "voice", 6, "text"))
    reference_text: str = field(default="", metadata=_desc(
        "reference_text", "参考音频对应的文字内容（动态音色必填）", "voice", 7, "text"))

    # ===== 输出 =====
    response_format: str = field(default="mp3", metadata=_desc(
        "response_format", "输出格式：mp3 / wav / pcm / opus", "output", 1, "select", ["mp3", "wav", "pcm", "opus"]))
    sample_rate: int = field(default=44100, metadata=_desc(
        "sample_rate", "采样率（mp3: 32000/44100；wav/pcm: 8000-44100；opus 固定 48000；0 表示用服务端默认）",
        "output", 2, "select", [0, 8000, 16000, 24000, 32000, 44100, 48000]))
    send_method: str = field(default="Voice", metadata=_desc(
        "send_method", "发送语音用的适配器方法名（默认 Voice；部分平台用 Record）", "output", 3, "text"))
    max_chars: int = field(default=500, metadata=_desc(
        "max_chars", "单段文本最大字符数（超长自动按句切分，0 不切分）", "output", 4, "number"))
    max_segments: int = field(default=3, metadata=_desc(
        "max_segments", "单次请求最多合成的段数（超出部分合并进最后一段）", "output", 5, "number"))

    # ===== 缓存 =====
    cache_enabled: bool = field(default=True, metadata=_desc(
        "cache_enabled", "合成结果按 文本+音色+参数 哈希缓存，重复内容不重复计费", "cache", 1, "switch"))
    cache_dir: str = field(default="data/TTS/audio", metadata=_desc(
        "cache_dir", "音频缓存目录", "cache", 2))
    cache_max_files: int = field(default=500, metadata=_desc(
        "cache_max_files", "缓存文件上限（超出按修改时间淘汰最旧，0 不限制）", "cache", 3, "number"))

    @classmethod
    def field_map(cls) -> dict:
        cached = cls.__dict__.get("_FIELD_MAP")
        if cached is None:
            cached = {f.name: f for f in dc_fields(cls)}
            cls._FIELD_MAP = cached
        return cached

    @classmethod
    def groups(cls) -> list[dict]:
        known = {g: meta.get("order", 99) for g, meta in GROUP_META.items()}
        for f in dc_fields(cls):
            g = str(((f.metadata or {}).get("ui") or {}).get("group") or "other")
            known.setdefault(g, 99)
        return [{"id": g, "order": o} for g, o in sorted(known.items(), key=lambda kv: (kv[1], kv[0]))]
