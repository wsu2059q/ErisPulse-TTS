from __future__ import annotations

_TEXTS: dict[str, dict[str, str]] = {
    "settings_title": {"zh-CN": "TTS 语音合成", "en": "TTS Speech"},
    "no_api_key": {
        "zh-CN": "未配置 API Key：请在 TTS 设置里填写 api_key",
        "en": "API key is not configured: set api_key in the TTS settings",
    },
    "empty_text": {"zh-CN": "要合成的文本为空", "en": "Text to synthesize is empty"},
    "synth_failed": {
        "zh-CN": "语音合成失败：{error}",
        "en": "Speech synthesis failed: {error}",
    },
    "synth_ok": {
        "zh-CN": "已合成 {n} 段语音（{chars} 字，{cached} 段命中缓存）：{path}",
        "en": "Synthesized {n} segment(s) ({chars} chars, {cached} cached): {path}",
    },
    "speak_ok": {
        "zh-CN": "已发送 {n} 条语音到 {target}",
        "en": "Sent {n} voice message(s) to {target}",
    },
    "speak_partial": {
        "zh-CN": "已发送 {ok}/{n} 条语音（{error}）",
        "en": "Sent {ok}/{n} voice message(s) ({error})",
    },
    "send_failed": {
        "zh-CN": "语音发送失败：{error}",
        "en": "Failed to send voice: {error}",
    },
    "bad_target": {
        "zh-CN": "目标不完整：需要 platform 与 target_id",
        "en": "Incomplete target: platform and target_id are required",
    },
    "voices_header": {
        "zh-CN": "系统预设音色（需带模型前缀使用）：",
        "en": "System preset voices (use with the model prefix):",
    },
    "custom_voices": {
        "zh-CN": "已上传音色（作为 voice 直接填 uri）：",
        "en": "Uploaded voices (pass the uri as voice):",
    },
    "no_custom_voices": {
        "zh-CN": "暂无已上传音色（克隆需要实名认证）",
        "en": "No uploaded voices yet (cloning requires real-name verification)",
    },
    "voice_list_failed": {
        "zh-CN": "获取音色列表失败：{error}",
        "en": "Failed to list voices: {error}",
    },
    "clone_need_name": {"zh-CN": "音色名称不能为空", "en": "Voice name is required"},
    "clone_need_audio": {"zh-CN": "参考音频不能为空", "en": "Reference audio is required"},
    "clone_need_text": {"zh-CN": "参考音频对应的文字不能为空", "en": "Reference transcript text is required"},
    "clone_ok": {
        "zh-CN": "音色已创建：{uri}（把它填到 default_voice 或作为 voice 参数使用）",
        "en": "Voice created: {uri} (use it as default_voice or the voice argument)",
    },
    "clone_failed": {"zh-CN": "创建音色失败：{error}", "en": "Failed to create voice: {error}"},
    "delete_need_uri": {"zh-CN": "uri 不能为空", "en": "uri is required"},
    "delete_ok": {"zh-CN": "音色已删除：{uri}", "en": "Voice deleted: {uri}"},
    "delete_failed": {"zh-CN": "删除音色失败：{error}", "en": "Failed to delete voice: {error}"},
    "audio_ref_invalid": {
        "zh-CN": "参考音频格式不支持：请给 http(s) URL、本地文件路径或 base64 字符串",
        "en": "Unsupported reference audio: provide an http(s) URL, a local file path or base64 data",
    },
    "model_hint": {
        "zh-CN": "当前模型：{model}；默认音色：{voice}",
        "en": "Model: {model}; default voice: {voice}",
    },
}


def t(key: str, default: str = "", **kwargs) -> str:
    entry = _TEXTS.get(key)
    if not entry:
        return default or key
    text = entry.get("zh-CN") or entry.get("en") or default or key
    try:
        return text.format(**kwargs)
    except (KeyError, IndexError):
        return text
