import json
import math
import os
import platformdirs

TIMINGS_PATH = os.path.join(platformdirs.user_config_dir("audio2text"), "timings.json")

CHUNK_DEFAULTS = {
    ("tiny", "cpu"): 15, ("tiny", "cuda"): 1,
    ("base", "cpu"): 30, ("base", "cuda"): 2,
    ("small", "cpu"): 60, ("small", "cuda"): 4,
    ("medium", "cpu"): 120, ("medium", "cuda"): 8,
    ("large-v1", "cpu"): 240, ("large-v1", "cuda"): 15,
    ("large-v2", "cpu"): 240, ("large-v2", "cuda"): 15,
    ("large-v3", "cpu"): 240, ("large-v3", "cuda"): 15,
    ("large", "cpu"): 240, ("large", "cuda"): 15,
    ("large-v3-turbo", "cpu"): 120, ("large-v3-turbo", "cuda"): 8,
    ("turbo", "cpu"): 120, ("turbo", "cuda"): 8,
    ("distil-large-v2", "cpu"): 100, ("distil-large-v2", "cuda"): 6,
    ("distil-large-v3", "cpu"): 130, ("distil-large-v3", "cuda"): 8,
    ("distil-large-v3.5", "cpu"): 100, ("distil-large-v3.5", "cuda"): 6,
}

STAGE_DEFAULTS = {
    "clean": {"cpu": 8.0, "cuda": 4.0},
    "align": {"cpu": 60.0, "cuda": 15.0},
    "diarize": {"cpu": 300.0, "cuda": 60.0},
}


class TimingDB:
    def __init__(self):
        self.data = self._load()

    def _load(self) -> dict:
        if os.path.exists(TIMINGS_PATH):
            try:
                with open(TIMINGS_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def save(self):
        os.makedirs(os.path.dirname(TIMINGS_PATH), exist_ok=True)
        with open(TIMINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _key(model_size: str, device: str) -> str:
        return f"{model_size}_{device}"

    def _default(self, key: str, stage: str) -> float:
        parts = key.split("_", 1)
        if len(parts) != 2:
            return 60.0
        model, device = parts
        if stage == "chunk":
            return CHUNK_DEFAULTS.get((model, device), 60.0)
        return STAGE_DEFAULTS.get(stage, {}).get(device, 60.0)

    def get(self, model_size: str, device: str, stage: str) -> float:
        entry = self.data.get(self._key(model_size, device), {})
        n = entry.get(f"{stage}_n", 0)
        if n > 0 and stage in entry:
            return entry[stage]
        return self._default(self._key(model_size, device), stage)

    def update(self, model_size: str, device: str, stage: str, elapsed: float):
        key = self._key(model_size, device)
        entry = self.data.setdefault(key, {})
        n = entry.get(f"{stage}_n", 0)
        prev = entry.get(stage, elapsed)
        entry[stage] = (prev * n + elapsed) / (n + 1)
        entry[f"{stage}_n"] = n + 1

    def predict(self, model_size: str, device: str,
                audio_duration_sec: float,
                chunk_minutes: int,
                do_align: bool, do_diarize: bool) -> dict:
        n_chunks = max(1, math.ceil(audio_duration_sec / 60 / chunk_minutes)
                       ) if chunk_minutes > 0 else 1
        chunk_t = self.get(model_size, device, "chunk") * n_chunks
        clean_t = self.get(model_size, device, "clean")
        align_t = self.get(model_size, device, "align") if do_align else 0
        diarize_t = self.get(model_size, device, "diarize") if do_diarize else 0
        total = clean_t + chunk_t + align_t + diarize_t
        return {
            "clean": clean_t, "transcribe": chunk_t,
            "align": align_t, "diarize": diarize_t,
            "total": total, "n_chunks": n_chunks,
        }
