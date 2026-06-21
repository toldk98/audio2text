import json
import math
import os
from workdirs import WorkDirs

TIMINGS_PATH = WorkDirs().timings_path

_RTF_STAGES = {"clean", "align", "diarize"}

CHUNK_DEFAULTS = {
    ("tiny", "cpu"): 15, ("tiny", "cuda"): 1,
    ("base", "cpu"): 30, ("base", "cuda"): 2,
    ("small", "cpu"): 60, ("small", "cuda"): 4,
    ("medium", "cpu"): 120, ("medium", "cuda"): 8,
    ("large-v1", "cpu"): 500, ("large-v1", "cuda"): 15,
    ("large-v2", "cpu"): 500, ("large-v2", "cuda"): 15,
    ("large-v3", "cpu"): 500, ("large-v3", "cuda"): 15,
    ("large", "cpu"): 500, ("large", "cuda"): 15,
    ("large-v3-turbo", "cpu"): 350, ("large-v3-turbo", "cuda"): 8,
    ("turbo", "cpu"): 350, ("turbo", "cuda"): 8,
    ("distil-large-v2", "cpu"): 200, ("distil-large-v2", "cuda"): 6,
    ("distil-large-v3", "cpu"): 250, ("distil-large-v3", "cuda"): 8,
    ("distil-large-v3.5", "cpu"): 200, ("distil-large-v3.5", "cuda"): 6,
}

STAGE_DEFAULTS = {
    "clean": {"cpu": 0.2, "cuda": 0.05},
    "split": {"cpu": 2.0, "cuda": 1.0},
    "merge": {"cpu": 5.0, "cuda": 2.0},
    "align": {"cpu": 6.0, "cuda": 0.5},
    "diarize": {"cpu": 2.5, "cuda": 0.3},
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

    def _default(self, key: str, stage: str, duration: float = 0) -> float:
        parts = key.split("_", 1)
        if len(parts) != 2:
            return 60.0
        model, device = parts
        if stage == "chunk":
            return CHUNK_DEFAULTS.get((model, device), 60.0)
        default = STAGE_DEFAULTS.get(stage, {}).get(device, 60.0)
        if stage in _RTF_STAGES and duration > 0:
            return default * duration
        return default

    def get(self, model_size: str, device: str, stage: str, duration: float = 0) -> float:
        key = self._key(model_size, device)
        entry = self.data.get(key, {})
        if stage in _RTF_STAGES:
            rtf = entry.get(f"{stage}_rtf")
            if rtf is not None and duration > 0:
                return rtf * duration
        n = entry.get(f"{stage}_n", 0)
        if n > 0 and stage in entry:
            return entry[stage]
        return self._default(key, stage, duration)

    def update(self, model_size: str, device: str, stage: str, elapsed: float, duration: float = 0):
        key = self._key(model_size, device)
        entry = self.data.setdefault(key, {})
        if stage in _RTF_STAGES and duration > 0:
            field = f"{stage}_rtf"
            value = elapsed / duration
        else:
            field = stage
            value = elapsed
        n = entry.get(f"{field}_n", 0)
        prev = entry.get(field, value)
        entry[field] = (prev * n + value) / (n + 1)
        entry[f"{field}_n"] = n + 1

    def predict(self, model_size: str, device: str,
                audio_duration_sec: float,
                chunk_minutes: int,
                do_align: bool, do_diarize: bool,
                do_clean: bool = True) -> dict:
        is_chunked = chunk_minutes > 0
        n_chunks = max(1, math.ceil(audio_duration_sec / 60 / chunk_minutes)
                       ) if is_chunked else 1
        clean_t = self.get(model_size, device, "clean", audio_duration_sec) if do_clean else 0
        split_t = self.get(model_size, device, "split") if is_chunked else 0
        chunk_t = self.get(model_size, device, "chunk") * n_chunks
        merge_t = self.get(model_size, device, "merge") if is_chunked else 0
        align_t = self.get(model_size, device, "align", audio_duration_sec) if do_align else 0
        diarize_t = self.get(model_size, device, "diarize", audio_duration_sec) if do_diarize else 0
        total = clean_t + split_t + chunk_t + merge_t + align_t + diarize_t
        return {
            "clean": clean_t,
            "split": split_t,
            "transcribe": chunk_t,
            "merge": merge_t,
            "align": align_t,
            "diarize": diarize_t,
            "total": total,
            "n_chunks": n_chunks,
        }
