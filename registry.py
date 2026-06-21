import json
import os
from datetime import datetime
from workdirs import WorkDirs

AUDIO_DIR = WorkDirs().audio_dir
REGISTRY_PATH = WorkDirs().registry_path
SUPPORTED_EXT = {".m4a", ".wav", ".mp3", ".ogg"}


def load_registry() -> list[dict]:
    if not os.path.exists(REGISTRY_PATH):
        return []
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            entries = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    for entry in entries:
        entry["status"] = "ok" if os.path.exists(entry["path"]) else "missing"
    return entries


def _save_registry(entries: list[dict]):
    os.makedirs(AUDIO_DIR, exist_ok=True)
    to_save = []
    for e in entries:
        to_save.append({"name": e["name"], "path": e["path"], "added": e.get("added")})
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(to_save, f, indent=2, ensure_ascii=False)


def add_external(path: str) -> str | None:
    path = os.path.abspath(path)
    if not os.path.exists(path):
        return "Файл не існує"
    ext = os.path.splitext(path)[1].lower()
    if ext not in SUPPORTED_EXT:
        return f"Формат {ext} не підтримується"
    if path.startswith(AUDIO_DIR):
        return "Файл вже в Audio/"

    entries = load_registry()
    for e in entries:
        if os.path.abspath(e["path"]) == path:
            return "Файл вже в реєстрі"

    name = os.path.splitext(os.path.basename(path))[0]
    entries.append({"name": name, "path": path, "added": datetime.now().isoformat()})
    _save_registry(entries)
    return None


def remove_entry(name: str) -> bool:
    entries = load_registry()
    new_entries = [e for e in entries if e["name"] != name]
    if len(new_entries) == len(entries):
        return False
    _save_registry(new_entries)
    return True


def list_external() -> list[dict]:
    entries = load_registry()
    return [e for e in entries if e["status"] == "ok"]


def list_dead() -> list[dict]:
    entries = load_registry()
    return [e for e in entries if e["status"] == "missing"]
