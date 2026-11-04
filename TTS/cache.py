"""音频文件缓存：相同文本/音色/参数不重复请求，避免重复计费。"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path


class AudioCache:
    def __init__(self, config, logger=None):
        self.config = config
        self.logger = logger

    def directory(self) -> Path:
        raw = str(getattr(self.config, "cache_dir", "") or "data/TTS/audio")
        return Path(raw).expanduser()

    @staticmethod
    def key(*parts: object) -> str:
        digest = hashlib.sha256()
        for part in parts:
            digest.update(str(part).encode("utf-8"))
            digest.update(b"\x00")
        return digest.hexdigest()[:32]

    def path_for(self, key: str, fmt: str) -> Path:
        suffix = str(fmt or "mp3").lower()
        return self.directory() / f"{key}.{suffix}"

    def read(self, key: str, fmt: str) -> Path | None:
        if not bool(getattr(self.config, "cache_enabled", True)):
            return None
        path = self.path_for(key, fmt)
        try:
            if path.is_file() and path.stat().st_size > 0:
                return path
        except OSError:
            return None
        return None

    def write(self, key: str, fmt: str, data: bytes) -> Path:
        path = self.path_for(key, fmt)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except OSError as e:
            if self.logger is not None:
                self.logger.warning(f"tts cache write failed: {e}")
        self.prune()
        return path

    def prune(self) -> int:
        """按修改时间淘汰最旧文件，返回删除数量。"""
        limit = int(getattr(self.config, "cache_max_files", 500) or 0)
        if limit <= 0:
            return 0
        directory = self.directory()
        try:
            files = [p for p in directory.glob("*") if p.is_file()]
        except OSError:
            return 0
        if len(files) <= limit:
            return 0
        files.sort(key=lambda p: p.stat().st_mtime)
        removed = 0
        for path in files[: len(files) - limit]:
            try:
                path.unlink()
                removed += 1
            except OSError:
                continue
        return removed

    def stats(self) -> dict:
        directory = self.directory()
        try:
            files = [p for p in directory.glob("*") if p.is_file()]
        except OSError:
            files = []
        total = sum(p.stat().st_size for p in files) if files else 0
        latest = max((p.stat().st_mtime for p in files), default=0.0)
        return {
            "files": len(files),
            "bytes": total,
            "last_write": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(latest)) if latest else "",
        }
