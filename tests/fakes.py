"""最小测试替身：sdk.client（aiohttp 风格）、adapter.Send、logger。"""

from __future__ import annotations

import asyncio


class FakeLogger:
    def __init__(self):
        self.records = []

    def _log(self, level, *args, **kwargs):
        self.records.append((level, " ".join(str(a) for a in args)))

    def debug(self, *args, **kwargs):
        self._log("debug", *args)

    def info(self, *args, **kwargs):
        self._log("info", *args)

    def warning(self, *args, **kwargs):
        self._log("warning", *args)

    error = warning

    def of_level(self, level):
        return [msg for lv, msg in self.records if lv == level]


class FakeLifecycle:
    def __init__(self):
        self.registered = []
        self.unregistered = []

    def register(self, event, handler, *_, **__):
        self.registered.append((event, handler))

    def unregister(self, event, handler=None, *_, **__):
        self.unregistered.append((event, handler))

    async def emit(self, event, data=None, **kwargs):
        current = data
        for evt, handler in self.registered:
            if evt != event:
                continue
            result = handler(current)
            if asyncio.iscoroutine(result):
                result = await result
            if result is not None:
                current = result
        return current


class FakeHTTPResponse:
    def __init__(self, status=200, body=b"", json_data=None):
        self.status = status
        self._body = body
        self._json = json_data

    async def read(self):
        return self._body

    async def json(self):
        if self._json is not None:
            return self._json
        raise ValueError("no json body")


class FakeHTTPClient:
    """记录每次请求；按 (method, path) 返回预置响应。"""

    def __init__(self, routes=None):
        self.routes = dict(routes or {})
        self.requests = []  # (method, url, kwargs)

    async def _do(self, method, url, **kwargs):
        from urllib.parse import urlparse

        self.requests.append((method, url, kwargs))
        path = urlparse(url).path or "/"
        for key, response in self.routes.items():
            route_method, route_path = key
            if route_method not in (method, "*"):
                continue
            # 后缀匹配：兼容 /v1 前缀与自定义 base_url
            if route_path == "*" or path == route_path or path.endswith(route_path):
                if callable(response):
                    response = response(kwargs)
                return response
        return FakeHTTPResponse(status=404, body=b"not found")

    async def get(self, url, **kwargs):
        return await self._do("get", url, **kwargs)

    async def post(self, url, **kwargs):
        return await self._do("post", url, **kwargs)


class FakeSendChain:
    def __init__(self, log, supports=("Text", "Voice")):
        self._log = log
        self._supports = tuple(supports)

    def To(self, target_type, target_id):
        self._log.append(("To", target_type, target_id))
        return self

    def _send(self, method, ref):
        self._log.append((method, ref))
        if method not in self._supports:
            raise AttributeError(f"method not supported: {method}")
        return {"status": "ok", "method": method}

    async def Text(self, content=""):
        return self._send("Text", content)

    async def Voice(self, ref=""):
        return self._send("Voice", ref)


class FakeAdapter:
    def __init__(self, name="onebot11"):
        self.name = name
        self.send_log = []

    @property
    def Send(self):
        return FakeSendChain(self.send_log)


class FakeAdapterManager:
    def __init__(self, adapters=None):
        self.adapters = dict(adapters or {})

    def get(self, platform):
        return self.adapters.get(platform)

    def list_sends(self, platform):
        return ["Text", "Voice"] if platform in self.adapters else []


class FakeSDK:
    def __init__(self, http=None, adapters=None):
        self.client = http or FakeHTTPClient()
        self.adapter = FakeAdapterManager(adapters)
        self.lifecycle = FakeLifecycle()
        self.logger = FakeLogger()


def make_config(**overrides):
    from TTS.Config import TTSConfig

    fields = TTSConfig.__dataclass_fields__
    bad = [k for k in overrides if k not in fields or k.startswith("_")]
    if bad:
        raise TypeError(f"unknown config keys: {bad}")
    return TTSConfig(**overrides)


def make_main(**overrides):
    """构造离线 Main：替换 sdk 为替身（不走框架单例）。"""
    from TTS.Main import Main

    main = Main()
    sdk = FakeSDK(adapters={"onebot11": FakeAdapter()})
    main.sdk = sdk
    config_overrides = {"api_key": "test-key"}
    config_overrides.update(overrides)
    main.cfg = make_config(**config_overrides)
    from TTS.cache import AudioCache
    from TTS.provider import SpeechClient

    main.logger = sdk.logger
    main.client = SpeechClient(sdk, main.cfg, sdk.logger)
    main.cache = AudioCache(main.cfg, sdk.logger)
    return main


async def drain(tasks):
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
