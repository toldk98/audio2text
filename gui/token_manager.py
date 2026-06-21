import os


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
    if mode == "keychain":
        import keyring
        keyring.set_password("audio2text", "hf_token", token)
    # mode == "ask": token stays in session memory only, no persistence


def has_keyring() -> bool:
    try:
        import keyring
        keyring.get_keyring()
        return True
    except Exception:
        return False
