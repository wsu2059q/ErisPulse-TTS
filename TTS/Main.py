"""ErisPulse-TTS 模块入口。

通用 OpenAI 兼容语音合成（默认 SiliconFlow CosyVoice2）：
合成、直接发语音、音色列表/克隆/删除，并实现 QvQChat 的 qvq_* 约定服务。
"""

from __future__ import annotations

try:
    from ErisPulse import sdk
except ImportError:  # 独立运行/测试环境兜底
    sdk = None

try:
    from ErisPulse.Core.Bases import BaseModule
except ImportError:  # pragma: no cover
    BaseModule = object  # type: ignore[assignment, misc]

try:
    from ErisPulse.Core.Bases import ModuleMeta
except ImportError:  # pragma: no cover
    ModuleMeta = None

try:
    from ErisPulse.loaders import ModuleLoadStrategy
except ImportError:  # pragma: no cover
    ModuleLoadStrategy = None

from .cache import AudioCache
from .Config import TTSConfig
from .provider import SpeechClient, resolve_base_url, system_voices
from .service import ACCESS, SCHEMAS, ServiceMixin

__version__ = "0.1.4"

SERVICES = [
    {
        "name": "tts_speak",
        "description": "把文本合成为语音并直接发送到指定会话；适合短句口语、角色扮演、深夜朗读；代码/长文/表格不要用语音。多账户后端建议留空 account 让调用方绑定，或显式传账户 id",
        "signature": "(text: str, platform: str, target_id: str, target_type: str = 'group', voice: str = '', speed: float = 0, emotion: str = '', account: str = '') -> str",
    },
    {
        "name": "tts_synthesize",
        "description": "只做语音合成并返回本地文件路径（不发送），供 send_message 的 audio_path 使用；相同文本命中缓存不重复计费",
        "signature": "(text: str, voice: str = '', speed: float = 0, emotion: str = '') -> dict",
    },
    {
        "name": "tts_voices",
        "description": "列出可用音色：系统预设 8 种 + 已上传克隆音色（uri）",
        "signature": "() -> dict",
    },
    {
        "name": "tts_clone",
        "description": "上传参考音频创建克隆音色（需服务商实名认证）；返回 uri 可直接作为 voice 使用",
        "signature": "(name: str, audio: str, text: str, model: str = '') -> dict",
    },
    {
        "name": "tts_delete_voice",
        "description": "删除已上传的克隆音色（传入克隆返回的 uri）",
        "signature": "(uri: str) -> dict",
    },
    {
        "name": "tts_status",
        "description": "TTS 运行状态：提供方/模型/默认音色/缓存统计",
        "signature": "() -> dict",
    },
    {
        "name": "qvq_schemas",
        "description": "约定服务：给 QvQChat 生态桥提供参数级 schema",
        "signature": "() -> dict",
    },
    {
        "name": "qvq_access",
        "description": "约定服务：自声明服务访问级别（tts_speak/synthesize/voices 对所有人开放，克隆/删除仅管理员）",
        "signature": "() -> dict",
    },
    {
        "name": "qvq_settings",
        "description": "归属标记：声明本模块出现在 QvQChat 设置页插件分区",
        "signature": "() -> dict",
    },
    {
        "name": "qvq_extensions",
        "description": "约定服务：向 QvQChat 注入语音使用建议（提示词），由 AI 自行判断何时用语音",
        "signature": "() -> dict",
    },
    {
        "name": "qvq_media",
        "description": "约定服务：声明本模块承接回复内联标记 [语音:文本]（QvQChat 投递层取合成文件后按会话代发；未声明时宿主按 tts_synthesize/tts_speak 服务名兜底）",
        "signature": "() -> dict",
    },
]

# 注入 QvQChat 系统提示的使用建议：只给判断依据，是否调用由 AI 决定
EXTENSION_PROMPTS = [
    {
        "text": (
            "发语音（原生能力）：用不用由你自己判断——短句口语、寒暄调侃、角色扮演、"
            "深夜闲聊、情绪上头，或用户明确想听声音时都合适；"
            "代码、表格、链接、长文和任务结果保持文字。"
            "首选写法：直接在回复里写 [语音:要说的话]，投递层会合成并按当前会话发出，"
            "不用调用工具；合成失败会自动改发文字。"
            "需要指定音色、语速、情绪或分成多段精细控制时，才走工具："
            "tts_synthesize(text) 返回的 path 是音频路径 → send_message(audio_path=该路径)，"
            "或 tts_speak(text, account=本账户) 一步直发（桥接工具名 eco_TTS_ 开头）。"
            "同一内容不要既发语音又发文字，不要反复重试或让用户干等。"
        ),
        "priority": 5,
    },
]


class Main(BaseModule, ServiceMixin):
    ConfigClass = TTSConfig

    def __init__(self):
        self.sdk = sdk
        self.cfg: TTSConfig = TTSConfig()
        self.logger = sdk.logger.get_child("TTS") if (sdk is not None and hasattr(sdk, "logger")) else None
        self.client = SpeechClient(sdk, self.cfg, self.logger)
        self.cache = AudioCache(self.cfg, self.logger)

    # ==================== 元信息 ====================

    @staticmethod
    def get_meta():
        info = dict(
            name="TTS",
            description="通用 TTS 语音合成：任意 OpenAI 兼容 /audio/speech（默认 SiliconFlow CosyVoice2），合成 / 发语音 / 音色克隆",
            version=__version__,
            group="智能",
            tags=["tts", "voice", "speech", "cosyvoice", "siliconflow", "qvq"],
            services=[dict(s) for s in SERVICES],
            min_sdk_version="2.8.0",
        )
        if ModuleMeta is not None:
            try:
                return ModuleMeta(**info)
            except Exception:
                return info
        return info

    @staticmethod
    def get_load_strategy():
        # 晚于 QvQChat（priority=50）：生态桥在 module.load 后自动刷新
        strategy = dict(lazy_load=False, priority=30)
        if ModuleLoadStrategy is not None:
            try:
                return ModuleLoadStrategy(**strategy)
            except Exception:
                return strategy
        return strategy

    # ==================== 生命周期 ====================

    async def on_load(self, event=None) -> bool:
        cfg = getattr(self, "cfg", None)
        if not isinstance(cfg, TTSConfig):
            self.cfg = TTSConfig()
        self.client = SpeechClient(self.sdk, self.cfg, self.logger)
        self.cache = AudioCache(self.cfg, self.logger)
        if not str(getattr(self.cfg, "api_key", "") or "").strip():
            if self.logger is not None:
                self.logger.warning("TTS api_key is empty: synthesis will fail until configured")
        if self.logger is not None:
            self.logger.info(
                f"TTS ready: provider={getattr(self.cfg, 'provider', '')} "
                f"base_url={resolve_base_url(self.cfg)} model={getattr(self.cfg, 'model', '')} "
                f"voices={len(system_voices(getattr(self.cfg, 'model', '')))}"
            )
        return True

    async def on_unload(self, event=None) -> bool:
        return True

    async def on_config_update(self, old, new) -> None:
        # 配置热更新后重建客户端/缓存（base_url、目录等可能变化）
        self.client = SpeechClient(self.sdk, self.cfg, self.logger)
        self.cache = AudioCache(self.cfg, self.logger)


__all__ = ["Main", "ACCESS", "SCHEMAS", "SERVICES", "__version__"]
