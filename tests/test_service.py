
from TTS.Main import Main, SERVICES
from TTS.service import ACCESS

from fakes import FakeHTTPClient, FakeHTTPResponse, make_main


def audio_route(data=b"AUDIO", status=200):
    return {("post", "/audio/speech"): FakeHTTPResponse(status, data if status == 200 else b"",
                                                        None if status == 200 else {"error": "boom"})}


async def test_synthesize_caches_identical_requests(tmp_path):
    http = FakeHTTPClient(routes=audio_route(b"MP3DATA"))
    main = make_main(cache_dir=str(tmp_path), cache_enabled=True)
    main.sdk.client = http
    main.client = type(main.client)(main.sdk, main.cfg, main.logger)
    first = await main.tts_synthesize("你好呀")
    second = await main.tts_synthesize("你好呀")
    assert first["ok"] and second["ok"]
    assert first["cached"] == 0 and second["cached"] == 1
    assert first["path"] == second["path"]
    assert len([r for r in http.requests if r[1].endswith("/audio/speech")]) == 1
    assert open(first["path"], "rb").read() == b"MP3DATA"


async def test_synthesize_splits_long_text(tmp_path):
    http = FakeHTTPClient(routes=audio_route())
    main = make_main(cache_dir=str(tmp_path), max_chars=10, max_segments=2)
    main.sdk.client = http
    main.client = type(main.client)(main.sdk, main.cfg, main.logger)
    result = await main.tts_synthesize("第一句话。第二句话。第三句话。")
    assert result["segments"] == 2
    assert len(result["files"]) == 2


async def test_synthesize_error_is_returned_not_raised(tmp_path):
    http = FakeHTTPClient(routes=audio_route(status=401))
    main = make_main(cache_dir=str(tmp_path))
    main.sdk.client = http
    main.client = type(main.client)(main.sdk, main.cfg, main.logger)
    result = await main.tts_synthesize("你好")
    assert result["ok"] is False
    assert "401" in result["error"]


async def test_tts_speak_sends_voice(tmp_path):
    http = FakeHTTPClient(routes=audio_route())
    main = make_main(cache_dir=str(tmp_path))
    main.sdk.client = http
    main.client = type(main.client)(main.sdk, main.cfg, main.logger)
    adapter = main.sdk.adapter.get("onebot11")
    reply = await main.tts_speak("晚上好", "onebot11", "g1", target_type="group")
    assert "已发送 1 条语音" in reply
    assert adapter.send_log[0] == ("To", "group", "g1")
    assert adapter.send_log[1][0] == "Voice"


async def test_tts_speak_private_alias_and_missing_target(tmp_path):
    http = FakeHTTPClient(routes=audio_route())
    main = make_main(cache_dir=str(tmp_path))
    main.sdk.client = http
    main.client = type(main.client)(main.sdk, main.cfg, main.logger)
    adapter = main.sdk.adapter.get("onebot11")
    await main.tts_speak("在吗", "onebot11", "u1", target_type="private")
    assert adapter.send_log[0] == ("To", "user", "u1")
    assert "目标不完整" in await main.tts_speak("x", "", "")


async def test_tts_voices_and_access_declaration(tmp_path):
    http = FakeHTTPClient(routes={
        ("get", "/audio/voice/list"): FakeHTTPResponse(200, json_data={"result": [
            {"uri": "speech:a:1:x", "customName": "我的"}
        ]}),
    })
    main = make_main(cache_dir=str(tmp_path), model="FunAudioLLM/CosyVoice2-0.5B")
    main.sdk.client = http
    main.client = type(main.client)(main.sdk, main.cfg, main.logger)
    result = await main.tts_voices()
    assert len(result["system"]) == 8 and result["system"][0]["voice"].endswith(":alex")
    assert result["custom"][0]["uri"] == "speech:a:1:x"
    assert ACCESS["tts_speak"] == "safe" and ACCESS["tts_clone"] == "admin"
    assert (await main.qvq_access())["tts_clone"] == "admin"
    assert "tts_speak" in await main.qvq_schemas()
    assert (await main.qvq_settings())["title"]


async def test_clone_validates_inputs_and_returns_uri(tmp_path):
    http = FakeHTTPClient(routes={
        ("post", "/uploads/audio/voice"): FakeHTTPResponse(200, json_data={"uri": "speech:new"}),
    })
    main = make_main(cache_dir=str(tmp_path))
    main.sdk.client = http
    main.client = type(main.client)(main.sdk, main.cfg, main.logger)
    assert (await main.tts_clone("", "u", "t"))["ok"] is False
    assert (await main.tts_clone("n", "", "t"))["ok"] is False
    assert (await main.tts_clone("n", "u", ""))["ok"] is False
    result = await main.tts_clone("新", "https://a.test/ref.mp3", "原文")
    assert result == {"ok": True, "uri": "speech:new", "message": result["message"]}


async def test_delete_voice_requires_uri(tmp_path):
    main = make_main(cache_dir=str(tmp_path))
    assert (await main.tts_delete_voice(""))["ok"] is False


def test_meta_services_cover_all_handlers():
    meta = Main.get_meta()
    info = meta if isinstance(meta, dict) else vars(meta)
    names = [s["name"] for s in info["services"]]
    assert names == [
        "tts_speak", "tts_synthesize", "tts_voices", "tts_clone",
        "tts_delete_voice", "tts_status", "qvq_schemas", "qvq_access", "qvq_settings",
        "qvq_extensions", "qvq_media",
    ]
    for entry in SERVICES:
        assert hasattr(Main, entry["name"]), entry["name"]


async def test_status_and_missing_api_key(tmp_path):
    main = make_main(cache_dir=str(tmp_path))
    status = await main.tts_status()
    assert status["ok"] is True and status["base_url"].endswith("/v1")
    main2 = make_main(cache_dir=str(tmp_path), api_key="")
    assert (await main2.tts_status())["ok"] is False
    result = await main2.tts_synthesize("x")
    assert result["ok"] is False
    assert "api_key" in result["error"].lower()


async def test_qvq_extensions_injects_usage_prompt():
    main = make_main()
    data = await main.qvq_extensions()
    assert isinstance(data.get("prompts"), list) and data["prompts"]
    text = data["prompts"][0]["text"]
    assert "tts_speak" in text
    assert "文字" in text or "text" in text.lower()


async def test_qvq_media_declares_voice_marker(tmp_path):
    main = make_main(cache_dir=str(tmp_path))
    data = await main.qvq_media()
    assert data["voice"]["service"] == "tts_synthesize"
    assert data["voice"]["mode"] == "produce"
    assert data["voice"]["path_keys"][0] == "files"
