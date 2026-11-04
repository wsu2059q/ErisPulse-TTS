"""OpenAI 兼容语音合成客户端（默认 SiliconFlow / CosyVoice2）。

只依赖 sdk.client（aiohttp 封装），不引入额外 SDK：
- POST {base}/audio/speech           合成（返回音频二进制）
- GET  {base}/audio/voice/list       音色列表
- POST {base}/uploads/audio/voice    上传/克隆音色
- POST {base}/audio/voice/deletions  删除音色
"""
from __future__ import annotations

import base64
import mimetypes
import re
from pathlib import Path

PRESETS = {
    "siliconflow": "https://api.siliconflow.cn/v1",
    "openai": "https://api.openai.com/v1",
}

# 硅基流动系统预置音色（使用时需带模型前缀，由 system_voices 拼接）
SYSTEM_VOICES = {
    "male": [("alex", "沉稳男声"), ("benjamin", "低沉男声"), ("charles", "磁性男声"), ("david", "欢快男声")],
    "female": [("anna", "沉稳女声"), ("bella", "激情女声"), ("claire", "温柔女声"), ("diana", "欢快女声")],
}

SENTENCE_RE = re.compile(r"[^。！？!?；;…\n]+[。！？!?；;…\n]?")


def resolve_base_url(config) -> str:
    explicit = str(getattr(config, "base_url", "") or "").strip()
    if explicit:
        return explicit.rstrip("/")
    provider = str(getattr(config, "provider", "siliconflow") or "siliconflow").lower()
    return PRESETS.get(provider, PRESETS["siliconflow"])


def system_voices(model: str) -> list[dict]:
    model = str(model or "")
    result: list[dict] = []
    for gender, items in SYSTEM_VOICES.items():
        for name, label in items:
            result.append({
                "voice": f"{model}:{name}" if model else name,
                "name": name,
                "label": label,
                "gender": gender,
            })
    return result


def split_text(text: str, max_chars: int = 500, max_segments: int = 3) -> list[str]:
    """按句子切分超长文本，最多 max_segments 段（超出合并进最后一段）。"""
    text = str(text or "").strip()
    if not text:
        return []
    limit = max(0, int(max_chars or 0))
    segments = max(1, int(max_segments or 1))
    if limit <= 0 or len(text) <= limit:
        return [text]
    chunks: list[str] = []
    buffer = ""
    for match in SENTENCE_RE.finditer(text):
        sentence = match.group(0)
        if buffer and len(buffer) + len(sentence) > limit:
            chunks.append(buffer.strip())
            buffer = ""
        # 单句本身超长：按硬边界切
        while len(sentence) > limit:
            chunks.append(sentence[:limit].strip())
            sentence = sentence[limit:]
        buffer += sentence
    if buffer.strip():
        chunks.append(buffer.strip())
    chunks = [c for c in chunks if c]
    if len(chunks) > segments:
        head = chunks[: segments - 1]
        head.append("".join(chunks[segments - 1:]))
        chunks = head
    return chunks


def audio_ref(raw: str) -> str:
    """参考音频 → 可直接放进请求的引用（URL 原样，本地文件转 data URL，base64 补 data 前缀）。"""
    text = str(raw or "").strip()
    if not text:
        return ""
    if text.startswith(("http://", "https://", "data:")):
        return text
    path = Path(text).expanduser()
    if path.is_file():
        mime = mimetypes.guess_type(str(path))[0] or "audio/mpeg"
        data = base64.b64encode(path.read_bytes()).decode()
        return f"data:{mime};base64,{data}"
    # 裸 base64
    if re.fullmatch(r"[A-Za-z0-9+/=\s]+", text) and len(text) > 64:
        return f"data:audio/mpeg;base64,{text}"
    raise ValueError(f"unsupported reference audio: {text[:40]}")


class SpeechError(RuntimeError):
    pass


class SpeechClient:
    def __init__(self, sdk, config, logger=None):
        self.sdk = sdk
        self.config = config
        self.logger = logger

    @property
    def base_url(self) -> str:
        return resolve_base_url(self.config)

    def _headers(self) -> dict:
        key = str(getattr(self.config, "api_key", "") or "").strip()
        if not key:
            raise SpeechError("missing api_key")
        return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    def _timeout(self) -> float:
        return float(getattr(self.config, "timeout", 60) or 60)

    async def _request(self, method: str, path: str, *, json_body: dict | None = None):
        client = getattr(self.sdk, "client", None)
        if client is None:
            raise SpeechError("sdk.client unavailable")
        url = f"{self.base_url}{path}"
        kwargs = {"headers": self._headers(), "timeout": self._timeout()}
        if json_body is not None:
            kwargs["json"] = json_body
        func = getattr(client, method)
        return await func(url, **kwargs)

    @staticmethod
    def _status(response) -> int:
        return int(getattr(response, "status", 200) or 200)

    async def _read_bytes(self, response) -> bytes:
        read = getattr(response, "read", None)
        return await read() if callable(read) else b""

    async def _error_detail(self, response, raw: bytes = b"") -> str:
        try:
            return str(await response.json())[:300]
        except Exception:
            try:
                return raw.decode("utf-8", errors="replace")[:300]
            except Exception:
                return ""

    # ==================== 合成 ====================

    def build_payload(self, text: str, voice: str = "", speed: float | None = None,
                      emotion: str = "") -> dict:
        payload: dict = {
            "model": str(getattr(self.config, "model", "") or ""),
            "input": str(text or ""),
            "response_format": str(getattr(self.config, "response_format", "mp3") or "mp3"),
        }
        resolved_voice = str(voice or getattr(self.config, "default_voice", "") or "").strip()
        # 动态音色：voice 留空 + references
        references = self._references()
        if resolved_voice:
            payload["voice"] = resolved_voice
        elif references:
            payload["voice"] = ""
            payload["references"] = references
        rate = speed if speed is not None else float(getattr(self.config, "speed", 1.0) or 1.0)
        if rate and abs(float(rate) - 1.0) > 1e-6:
            payload["speed"] = float(rate)
        gain = float(getattr(self.config, "gain", 0.0) or 0.0)
        if gain:
            payload["gain"] = gain
        rate_hz = int(getattr(self.config, "sample_rate", 0) or 0)
        if rate_hz:
            payload["sample_rate"] = rate_hz
        style = self._emotion_prefix(emotion)
        if style:
            payload["input"] = style + payload["input"]
        return payload

    def _emotion_prefix(self, emotion: str) -> str:
        emotion = str(emotion or "").strip()
        template = str(getattr(self.config, "emotion_template", "") or "").strip()
        if not emotion or not template:
            return ""
        try:
            instruction = template.format(emotion=emotion)
        except (KeyError, IndexError):
            instruction = f"{template}{emotion}"
        return instruction + "<|endofprompt|>"

    def _references(self) -> list[dict]:
        raw = str(getattr(self.config, "reference_audio", "") or "").strip()
        if not raw:
            return []
        return [{"audio": audio_ref(raw), "text": str(getattr(self.config, "reference_text", "") or "")}]

    async def synthesize(self, text: str, voice: str = "", speed: float | None = None,
                         emotion: str = "") -> bytes:
        payload = self.build_payload(text, voice=voice, speed=speed, emotion=emotion)
        response = await self._request("post", "/audio/speech", json_body=payload)
        status = self._status(response)
        if status == 200:
            raw = await self._read_bytes(response)
            if raw:
                return raw
        raw = await self._read_bytes(response) if status != 200 else b""
        raise SpeechError(f"HTTP {status} {await self._error_detail(response, raw)}".strip())

    # ==================== 音色管理 ====================

    async def list_voices(self) -> list[dict]:
        response = await self._request("get", "/audio/voice/list")
        status = self._status(response)
        if status != 200:
            raise SpeechError(f"HTTP {status}")
        data = await response.json()
        items = data
        if isinstance(data, dict):
            items = data.get("result") or data.get("data") or data.get("voices") or []
        result = []
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict):
                uri = str(item.get("uri") or "")
                if uri:
                    result.append({
                        "uri": uri,
                        "name": str(item.get("customName") or item.get("name") or ""),
                        "model": str(item.get("model") or ""),
                    })
        return result

    async def clone_voice(self, name: str, audio: str, text: str, model: str = "") -> str:
        payload = {
            "model": str(model or getattr(self.config, "model", "") or ""),
            "customName": str(name or ""),
            "audio": audio_ref(audio),
            "text": str(text or ""),
        }
        response = await self._request("post", "/uploads/audio/voice", json_body=payload)
        status = self._status(response)
        if status not in (200, 201):
            raise SpeechError(f"HTTP {status} {await self._error_detail(response)}".strip())
        data = await response.json()
        if isinstance(data, dict):
            return str(data.get("uri") or "")
        return ""

    async def delete_voice(self, uri: str) -> bool:
        response = await self._request("post", "/audio/voice/deletions", json_body={"uri": str(uri or "")})
        status = self._status(response)
        if status not in (200, 204):
            raise SpeechError(f"HTTP {status}")
        return True
