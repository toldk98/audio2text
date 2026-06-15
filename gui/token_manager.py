import json
import os

import platformdirs

SETTINGS_PATH = os.path.join(platformdirs.user_config_dir("audio2text"), "settings.json")
MODE_PATH = os.path.join(platformdirs.user_config_dir("audio2text"), "token_storage_mode.txt")

MODES = {"keychain": "системне сховище (keychain)",
         "file":     "файл налаштувань (settings.json)",
         "ask":      "питати кожен запуск"}


def load_token() -> tuple[str | None, str | None]:
    token_env = os.getenv("HF_TOKEN")
    if token_env:
        return token_env, "env"

    try:
        import keyring
        token = keyring.get_password("audio2text", "hf_token")
        if token:
            return token, "keychain"
    except Exception:
        pass

    if os.path.exists(SETTINGS_PATH):
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        token = data.get("hf_token")
        if token:
            return token, "file"

    return None, None


def save_token(token: str, mode: str):
    if mode == "keychain":
        import keyring
        keyring.set_password("audio2text", "hf_token", token)
    elif mode == "file":
        data = {}
        if os.path.exists(SETTINGS_PATH):
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        data["hf_token"] = token
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    os.makedirs(os.path.dirname(MODE_PATH), exist_ok=True)
    with open(MODE_PATH, "w") as f:
        f.write(mode)


def get_storage_mode() -> str | None:
    if os.path.exists(MODE_PATH):
        with open(MODE_PATH) as f:
            return f.read().strip()
    return None


def has_keyring() -> bool:
    try:
        import keyring
        keyring.get_keyring()
        return True
    except Exception:
        return False
