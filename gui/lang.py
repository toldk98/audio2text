import json
import os
import threading

from settings import load_settings

LOCALES_DIR = os.path.join(os.path.dirname(__file__), "locales")
_FALLBACK_LANG = "en"


class Lang:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    def __init__(self, lang: str | None = None):
        if hasattr(self, "_loaded"):
            return
        self._loaded = True
        if lang is None:
            lang = self._restore()
        self._lang = lang
        self._data: dict = {}
        self._fallback: dict = {}
        self._load(self._lang)

    def _load(self, lang: str):
        self._data = self._read_file(lang) or {}
        self._fallback = self._read_file(_FALLBACK_LANG) or {}

    def _read_file(self, lang: str) -> dict | None:
        path = os.path.join(LOCALES_DIR, f"{lang}.json")
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _restore(self) -> str:
        return load_settings().get("lang", "uk")

    @property
    def current(self) -> str:
        return self._lang

    def switch_to(self, lang: str):
        self._lang = lang
        self._load(lang)

    def get(self, key: str, **kwargs) -> str:
        val = self._data.get(key) or self._fallback.get(key)
        if val is None:
            return f"?{key}?"
        if kwargs:
            return val.format(**kwargs)
        return val

    def __getitem__(self, key: str) -> str:
        return self.get(key)


_inst = Lang()
_ = _inst.get
