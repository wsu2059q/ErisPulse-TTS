import base64

import pytest

from TTS.provider import (
    SpeechClient,
    SpeechError,
    audio_ref,
    resolve_base_url,
    split_text,
    system_voices,
)

from fakes import FakeHTTPClient, FakeHTTPResponse, FakeSDK, make_config


def make_client(**cfg):
    config = make_config(**cfg)
    sdk = FakeSDK()
    return SpeechClient(sdk, config), config, sdk


def test_base_url_presets_and_override():
    assert resolve_base_url(make_config(provider="siliconflow")) == "https://api.siliconflow.cn/v1"
    assert resolve_base_url(make_config(provider="openai")) == "https://api.openai.com/v1"
    assert resolve_base_url(make_config(provider="custom", base_url="https://x.test/v1/")) == "https://x.test/v1"


def test_system_voices_are_model_prefixed():
    voices = system_voices("FunAudioLLM/CosyVoice2-0.5B")
    assert len(voices) == 8
    assert {"voice": "FunAudioLLM/CosyVoice2-0.5B:alex", "gender": "male"}.items() <= voices[0].items()


def test_split_text_by_sentence_with_segment_cap():
    text = "第一句。" * 20
    chunks = split_text(text, max_chars=20, max_segments=3)
    assert len(chunks) == 3
    assert sum(len(c) for c in chunks) == len(text)
    assert chunks[0].endswith("。")


def test_split_text_short_and_disabled():
    assert split_text("短句", max_chars=500) == ["短句"]
    long = "字" * 50
    assert split_text(long, max_chars=0) == [long]


def test_audio_ref_forms(tmp_path):
    assert audio_ref("https://a.test/x.mp3") == "https://a.test/x.mp3"
    path = tmp_path / "ref.mp3"
    path.write_bytes(b"ID3fake")
    data_url = audio_ref(str(path))
    assert data_url.startswith("data:audio/")
    assert base64.b64decode(data_url.split(",", 1)[1]) == b"ID3fake"
    raw = base64.b64encode(b"x" * 80).decode()
    assert audio_ref(raw).startswith("data:audio/mpeg;base64,")
    with pytest.raises(ValueError):
        audio_ref("not-a-file-or-url")


def test_build_payload_basics():
    client, _, _ = make_client(model="m", default_voice="m:alex", response_format="mp3",
                               sample_rate=44100, speed=1.0, gain=2.0)
    payload = client.build_payload("你好", speed=None)
    assert payload["model"] == "m"
    assert payload["input"] == "你好"
    assert payload["voice"] == "m:alex"
    assert payload["response_format"] == "mp3"
    assert payload["sample_rate"] == 44100
    assert payload["gain"] == 2.0
    assert "speed" not in payload  # 1.0 不显式传递


def test_build_payload_emotion_and_dynamic_voice():
    client, _, _ = make_client(model="m", default_voice="", reference_audio="https://a.test/ref.mp3",
                               reference_text="原文", emotion_template="用{emotion}的情感说")
    payload = client.build_payload("正文", emotion="高兴")
    assert payload["voice"] == ""
    assert payload["references"][0]["audio"] == "https://a.test/ref.mp3"
    assert payload["input"].startswith("用高兴的情感说<|endofprompt|>")


async def test_synthesize_returns_bytes_and_posts_payload():
    http = FakeHTTPClient(routes={("post", "/audio/speech"): FakeHTTPResponse(200, b"AUDIO")})
    client = SpeechClient(FakeSDK(http=http), make_config(api_key="k"), None)
    data = await client.synthesize("你好", voice="m:alex")
    assert data == b"AUDIO"
    method, url, kwargs = http.requests[0]
    assert method == "post" and url.endswith("/audio/speech")
    assert kwargs["json"]["input"] == "你好"
    assert kwargs["headers"]["Authorization"] == "Bearer k"


async def test_synthesize_error_includes_status():
    http = FakeHTTPClient(routes={("post", "/audio/speech"):
                                  FakeHTTPResponse(401, b"", {"error": "bad key"})})
    client = SpeechClient(FakeSDK(http=http), make_config(api_key="k"), None)
    with pytest.raises(SpeechError) as exc:
        await client.synthesize("x")
    assert "401" in str(exc.value) and "bad key" in str(exc.value)


async def test_synthesize_requires_api_key():
    client = SpeechClient(FakeSDK(), make_config(api_key=""), None)
    with pytest.raises(SpeechError):
        await client.synthesize("x")


async def test_list_voices_parses_shapes():
    http = FakeHTTPClient(routes={("get", "/audio/voice/list"): FakeHTTPResponse(
        200, json_data={"result": [{"uri": "speech:a:1:x", "customName": "我的音色", "model": "m"}]})})
    client = SpeechClient(FakeSDK(http=http), make_config(api_key="k"), None)
    voices = await client.list_voices()
    assert voices == [{"uri": "speech:a:1:x", "name": "我的音色", "model": "m"}]


async def test_clone_and_delete():
    http = FakeHTTPClient(routes={
        ("post", "/uploads/audio/voice"): FakeHTTPResponse(200, json_data={"uri": "speech:new"}),
        ("post", "/audio/voice/deletions"): FakeHTTPResponse(200, json_data={}),
    })
    client = SpeechClient(FakeSDK(http=http), make_config(api_key="k"), None)
    uri = await client.clone_voice("新音色", "https://a.test/ref.mp3", "原文")
    assert uri == "speech:new"
    assert (await client.delete_voice(uri)) is True
    clone_payload = http.requests[0][2]["json"]
    assert clone_payload["customName"] == "新音色"
    assert clone_payload["audio"] == "https://a.test/ref.mp3"
