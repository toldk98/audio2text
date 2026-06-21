import json
import os
import secrets
import shutil
from datetime import datetime
from workdirs import WorkDirs


class SessionDir:
    _base_dir: str | None = None

    @classmethod
    def _default_base(cls) -> str:
        if cls._base_dir is None:
            cls._base_dir = WorkDirs().cache_dir
        return cls._base_dir

    def __init__(self, input_path: str, base_dir: str | None = None):
        name = os.path.splitext(os.path.basename(input_path))[0]
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        rand = secrets.token_hex(4)
        self.session_id = f"{name}_{ts}_{rand}"
        if base_dir is None:
            base_dir = self._default_base()
        self.path = os.path.join(base_dir, self.session_id)
        os.makedirs(self.path, exist_ok=True)
        self._cleaned_audio = os.path.join(self.path, "cleaned.wav")

    @classmethod
    def find_existing(cls, input_path: str, base_dir: str | None = None) -> "SessionDir | None":
        name = os.path.splitext(os.path.basename(input_path))[0]
        if base_dir is None:
            base_dir = cls._default_base()
        if not os.path.isdir(base_dir):
            return None
        matching = sorted(
            d for d in os.listdir(base_dir)
            if d.startswith(f"{name}_") and os.path.isdir(os.path.join(base_dir, d))
        )
        if not matching:
            return None
        latest = matching[-1]
        wd = cls.__new__(cls)
        wd.path = os.path.join(base_dir, latest)
        wd.session_id = latest
        wd._cleaned_audio = os.path.join(wd.path, "cleaned.wav")
        return wd

    @property
    def cleaned_audio(self) -> str:
        return self._cleaned_audio

    @property
    def cleaned_exists(self) -> bool:
        return os.path.exists(self._cleaned_audio)

    @property
    def chunks_dir(self) -> str:
        return os.path.join(self.path, "chunks")

    def ensure_chunks_dir(self):
        os.makedirs(self.chunks_dir, exist_ok=True)
        return self.chunks_dir

    @property
    def chunks_exist(self) -> bool:
        return os.path.isdir(self.chunks_dir) and any(
            f.endswith(".wav") for f in os.listdir(self.chunks_dir)
        )

    @property
    def transcribed_dir(self) -> str:
        return os.path.join(self.path, "transcribed")

    def transcribed_chunk_keys(self) -> set[str]:
        if not os.path.isdir(self.transcribed_dir):
            return set()
        return {
            os.path.splitext(f)[0]
            for f in os.listdir(self.transcribed_dir)
            if f.endswith(".json")
        }

    def save_transcribed_chunk(self, chunk_key: str, segments: list[dict]):
        os.makedirs(self.transcribed_dir, exist_ok=True)
        path = os.path.join(self.transcribed_dir, f"{chunk_key}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(segments, f, ensure_ascii=False, indent=2)

    @property
    def merged_json(self) -> str:
        return os.path.join(self.path, "merged.json")

    @property
    def merged_exists(self) -> bool:
        return os.path.exists(self.merged_json)

    @property
    def aligned_json(self) -> str:
        return os.path.join(self.path, "aligned.json")

    @property
    def aligned_exists(self) -> bool:
        return os.path.exists(self.aligned_json)

    @property
    def final_txt(self) -> str:
        return os.path.join(self.path, "result.txt")

    def save_json(self, data: dict | list, filename: str) -> str:
        path = os.path.join(self.path, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path

    def load_json(self, filename: str) -> dict | list | None:
        path = os.path.join(self.path, filename)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def cleanup(self):
        if os.path.isdir(self.path):
            shutil.rmtree(self.path, ignore_errors=True)
