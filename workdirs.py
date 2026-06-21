import os
import platformdirs


class WorkDirs:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_init"):
            return
        self._init = True
        self._config_dir = platformdirs.user_config_dir("audio2text")
        self._cache_dir = platformdirs.user_cache_dir("audio2text")
        self._data_dir = platformdirs.user_data_dir("audio2text")
        self._log_dir = platformdirs.user_log_dir("audio2text")
        self._whisper_cache = os.path.join(os.path.expanduser("~"), ".cache", "whisper")
        self._hf_hub = os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub")

    @property
    def config_dir(self) -> str:
        return self._config_dir

    @property
    def settings_path(self) -> str:
        return os.path.join(self._config_dir, "settings.json")

    @property
    def profiles_path(self) -> str:
        return os.path.join(self._config_dir, "profiles.yaml")

    @property
    def timings_path(self) -> str:
        return os.path.join(self._config_dir, "timings.json")

    @property
    def cache_dir(self) -> str:
        return self._cache_dir

    @property
    def data_dir(self) -> str:
        return self._data_dir

    @property
    def registry_path(self) -> str:
        return os.path.join(self._data_dir, "external_registry.json")

    @property
    def audio_dir(self) -> str:
        return self._data_dir

    @property
    def log_dir(self) -> str:
        return self._log_dir

    @property
    def log_path(self) -> str:
        return os.path.join(self._log_dir, "audio2text.log")

    @property
    def whisper_cache(self) -> str:
        return self._whisper_cache

    @property
    def hf_hub(self) -> str:
        return self._hf_hub

    def ensure_all(self):
        for d in (self._config_dir, self._cache_dir, self._data_dir, self._log_dir):
            os.makedirs(d, exist_ok=True)
