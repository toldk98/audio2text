import json
import os

import platformdirs

SETTINGS_PATH = os.path.join(platformdirs.user_config_dir("audio2text"), "settings.json")

def _token_modes():
    from gui.lang import _
    return {"keychain": _("token.mode_keychain"),
            "ask":      _("token.mode_ask")}


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

    return None, None


def save_token(token: str, mode: str):
    import keyring
    keyring.set_password("audio2text", "hf_token", token)


def has_keyring() -> bool:
    try:
        import keyring
        keyring.get_keyring()
        return True
    except Exception:
        return False


def load_settings() -> dict:
    if os.path.exists(SETTINGS_PATH):
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_settings(data: dict):
    existing = {}
    if os.path.exists(SETTINGS_PATH):
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            existing = json.load(f)
    existing.update(data)
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)
