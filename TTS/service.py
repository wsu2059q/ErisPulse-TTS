"""对外服务：合成、发语音、音色列表/克隆/删除，以及 QvQChat 生态约定服务。"""
from __future__ import annotations

import asyncio
from pathlib import Path

from . import texts
from .cache import AudioCache
from .provider import SpeechClient, SpeechError, split_text, system_voices

# QvQChat 生态约定：模块自声明访问级别
ACCESS = {
    "tts_speak": "safe",
    "tts_synthesize": "safe",
    "tts_voices": "safe",
    "tts_clone": "admin",
    "tts_delete_voice": "admin",
    "tts_status": "safe",
}

SCHEMAS = {
    "tts_speak": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "要朗读的文本（建议短句口语；不要朗读代码/表格/Markdown 标记）"},
            "platform": {"type": "string", "description": "目标平台名（如 onebot11）"},
            "target_id": {"type": "string", "description": "目标会话 id（群号或用户号）"},
            "target_type": {"type": "string", "enum": ["group", "user"], "description": "群聊 group / 私聊 user", "default": "group"},
            "voice": {"type": "string", "description": "音色（系统预设需带模型前缀，或克隆音色的 uri；留空用默认音色）"},
            "speed": {"type": "number", "description": "语速 0.25-4.0，留空用配置"},
            "emotion": {"type": "string", "description": "情感（如 高兴/悲伤/温柔；SiliconFlow CosyVoice 支持，其他提供方忽略）"},
        },
        "required": ["text", "platform", "target_id"],
    },
    "tts_synthesize": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "要合成的文本"},
            "voice": {"type": "string", "description": "音色（留空用默认）"},
            "speed": {"type": "number", "description": "语速 0.25-4.0"},
            "emotion": {"type": "string", "description": "情感"},
        },
        "required": ["text"],
    },
    "tts_clone": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "音色名称（自定义标识）"},
            "audio": {"type": "string", "description": "参考音频：http(s) URL、本地文件路径或 base64（建议 8-10 秒、单人、无噪音）"},
            "text": {"type": "string", "description": "参考音频里说的原文"},
            "model": {"type": "string", "description": "模型名，留空用配置"},
        },
        "required": ["name", "audio", "text"],
    },
    "tts_delete_voice": {
        "type": "object",
        "properties": {"uri": {"type": "string", "description": "克隆音色返回的 uri"}},
        "required": ["uri"],
    },
}


def _normalize_target(target_type: str) -> str:
    value = str(target_type or "group").strip().lower()
    if value in ("group", "channel", "channel_group"):
        return "group"
    if value in ("user", "private", "friend"):
        return "user"
    return "group"


class ServiceMixin:
    """Main 的服务 mixin。依赖宿主提供 sdk / cfg / logger / client / cache。"""

    # ==================== 合成核心 ====================

    async def _synthesize_segments(self, text: str, voice: str = "", speed=None, emotion: str = "") -> tuple[list[str], int, int]:
        """合成（带缓存），返回 (文件路径列表, 字符数, 缓存命中数)。"""
        chunks = split_text(
            text,
            max_chars=int(getattr(self.cfg, "max_chars", 500) or 0),
            max_segments=int(getattr(self.cfg, "max_segments", 3) or 1),
        )
        if not chunks:
            return [], 0, 0
        fmt = str(getattr(self.cfg, "response_format", "mp3") or "mp3")
        effective_voice = str(voice or getattr(self.cfg, "default_voice", "") or "")
        rate = speed if speed is not None else float(getattr(self.cfg, "speed", 1.0) or 1.0)
        paths: list[str] = []
        cached = 0
        for chunk in chunks:
            key = AudioCache.key(
                self.client.base_url, getattr(self.cfg, "model", ""), effective_voice,
                rate, emotion, fmt, chunk,
            )
            hit = self.cache.read(key, fmt)
            if hit is not None:
                cached += 1
                paths.append(str(hit))
                continue
            data = await self.client.synthesize(chunk, voice=voice, speed=rate, emotion=emotion)
            path = self.cache.write(key, fmt, data)
            paths.append(str(path))
        return paths, len("".join(chunks)), cached

    # ==================== 服务实现 ====================

    async def tts_synthesize(self, text: str = "", voice: str = "", speed=None, emotion: str = "", **_) -> dict:
        text = str(text or "").strip()
        if not text:
            return {"ok": False, "error": texts.t("empty_text")}
        try:
            paths, chars, cached = await self._synthesize_segments(text, voice=voice, speed=speed, emotion=emotion)
        except SpeechError as e:
            return {"ok": False, "error": texts.t("synth_failed", error=e)}
        except Exception as e:
            self.logger.warning(f"tts synthesize failed: {e}")
            return {"ok": False, "error": texts.t("synth_failed", error=f"{type(e).__name__}: {e}")}
        return {
            "ok": bool(paths),
            "path": paths[0] if paths else "",
            "files": paths,
            "chars": chars,
            "cached": cached,
            "segments": len(paths),
        }

    async def tts_speak(self, text: str = "", platform: str = "", target_id: str = "",
                        target_type: str = "group", voice: str = "", speed=None,
                        emotion: str = "", **_) -> str:
        text = str(text or "").strip()
        if not text:
            return texts.t("empty_text")
        platform = str(platform or "").strip()
        target_id = str(target_id or "").strip()
        if not platform or not target_id:
            return texts.t("bad_target")
        adapter = self.sdk.adapter.get(platform)
        if adapter is None:
            return texts.t("send_failed", error=f"adapter not found: {platform}")
        try:
            paths, _, _ = await self._synthesize_segments(text, voice=voice, speed=speed, emotion=emotion)
        except SpeechError as e:
            return texts.t("synth_failed", error=e)
        except Exception as e:
            self.logger.warning(f"tts speak failed: {e}")
            return texts.t("synth_failed", error=f"{type(e).__name__}: {e}")
        if not paths:
            return texts.t("empty_text")

        method = str(getattr(self.cfg, "send_method", "Voice") or "Voice")
        target = _normalize_target(target_type)
        sent = 0
        last_error = ""
        for path in paths:
            try:
                chain = adapter.Send.To(target, target_id)
                sender = getattr(chain, method, None)
                if sender is None:
                    last_error = f"adapter has no send method: {method}"
                    break
                result = sender(path)
                if asyncio.iscoroutine(result):
                    result = await result
                if isinstance(result, dict) and str(result.get("status") or "") == "failed":
                    last_error = str(result)[:200]
                    break
                sent += 1
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                break
        if sent == len(paths):
            return texts.t("speak_ok", n=sent, target=f"{platform}/{target}/{target_id}")
        if sent:
            return texts.t("speak_partial", ok=sent, n=len(paths), error=last_error)
        return texts.t("send_failed", error=last_error or "unknown")

    async def tts_voices(self, **_) -> dict:
        model = str(getattr(self.cfg, "model", "") or "")
        result = {
            "ok": True,
            "model": model,
            "default_voice": str(getattr(self.cfg, "default_voice", "") or ""),
            "system": system_voices(model),
            "custom": [],
        }
        try:
            result["custom"] = await self.client.list_voices()
        except Exception as e:
            result["ok"] = False
            result["error"] = texts.t("voice_list_failed", error=e)
        return result

    async def tts_clone(self, name: str = "", audio: str = "", text: str = "", model: str = "", **_) -> dict:
        name = str(name or "").strip()
        audio = str(audio or "").strip()
        text = str(text or "").strip()
        if not name:
            return {"ok": False, "error": texts.t("clone_need_name")}
        if not audio:
            return {"ok": False, "error": texts.t("clone_need_audio")}
        if not text:
            return {"ok": False, "error": texts.t("clone_need_text")}
        try:
            uri = await self.client.clone_voice(name, audio, text, model=model)
        except ValueError as e:
            return {"ok": False, "error": texts.t("audio_ref_invalid") + f" ({e})"}
        except Exception as e:
            return {"ok": False, "error": texts.t("clone_failed", error=e)}
        if not uri:
            return {"ok": False, "error": texts.t("clone_failed", error="empty uri")}
        return {"ok": True, "uri": uri, "message": texts.t("clone_ok", uri=uri)}

    async def tts_delete_voice(self, uri: str = "", **_) -> dict:
        uri = str(uri or "").strip()
        if not uri:
            return {"ok": False, "error": texts.t("delete_need_uri")}
        try:
            await self.client.delete_voice(uri)
        except Exception as e:
            return {"ok": False, "error": texts.t("delete_failed", error=e)}
        return {"ok": True, "message": texts.t("delete_ok", uri=uri)}

    async def tts_status(self, **_) -> dict:
        return {
            "ok": bool(str(getattr(self.cfg, "api_key", "") or "").strip()),
            "provider": str(getattr(self.cfg, "provider", "") or ""),
            "base_url": self.client.base_url,
            "model": str(getattr(self.cfg, "model", "") or ""),
            "default_voice": str(getattr(self.cfg, "default_voice", "") or ""),
            "response_format": str(getattr(self.cfg, "response_format", "") or ""),
            "cache": self.cache.stats(),
            "hint": texts.t(
                "model_hint",
                model=getattr(self.cfg, "model", ""),
                voice=getattr(self.cfg, "default_voice", "") or "(dynamic reference)",
            ),
        }

    # ==================== QvQChat 约定服务 ====================

    async def qvq_schemas(self, **_) -> dict:
        return {name: dict(schema) for name, schema in SCHEMAS.items()}

    async def qvq_access(self, **_) -> dict:
        return dict(ACCESS)

    async def qvq_settings(self, **_) -> dict:
        return {"title": texts.t("settings_title")}

    async def qvq_extensions(self, **_) -> dict:
        """QvQChat 统一扩展入口：注入语音使用建议（提示词），AI 自行判断是否调用。"""
        from .Main import EXTENSION_PROMPTS

        return {"prompts": [dict(item) for item in EXTENSION_PROMPTS]}


def output_dir(config) -> Path:
    return Path(str(getattr(config, "cache_dir", "") or "data/TTS/audio")).expanduser()


__all__ = ["ServiceMixin", "ACCESS", "SCHEMAS", "SpeechClient", "AudioCache", "output_dir"]
