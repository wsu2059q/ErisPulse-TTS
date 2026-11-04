"""ErisPulse-TTS：通用 OpenAI 兼容语音合成插件。

- 默认接 SiliconFlow（FunAudioLLM/CosyVoice2-0.5B），也支持 OpenAI 与任意兼容端点
- 服务：tts_speak（合成+发语音）/ tts_synthesize（返回文件）/ tts_voices /
  tts_clone / tts_delete_voice / tts_status
- 实现 QvQChat 约定：qvq_schemas / qvq_access / qvq_settings
"""

from .Main import Main, __version__

__all__ = ["Main", "__version__"]
