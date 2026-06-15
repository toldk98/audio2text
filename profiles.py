import os
import platformdirs

try:
    import yaml
except ImportError:
    yaml = None

USER_PROFILES_PATH = os.path.join(platformdirs.user_config_dir("audio2text"), "profiles.yaml")

EMBEDDED_PROFILES = {
    "file": {
        "tiny": {
            "quick_uk": {
                "description": "Швидка транскрипція (tiny), без діаризації",
                "language": "uk",
                "clean_mode": "temp",
                "post_action": "delete",
                "align": False,
                "diarize": False,
            }
        },
        "base": {
            "base_uk": {
                "description": "Базова транскрипція (base), без діаризації",
                "language": "uk",
                "clean_mode": "temp",
                "post_action": "delete",
                "align": True,
                "diarize": False,
            }
        },
        "small": {
            "small_uk": {
                "description": "Транскрипція (small), без діаризації",
                "language": "uk",
                "clean_mode": "temp",
                "post_action": "delete",
                "align": True,
                "diarize": False,
            }
        },
        "medium": {
            "medium_uk": {
                "description": "Транскрипція (medium), без діаризації",
                "language": "uk",
                "clean_mode": "temp",
                "post_action": "delete",
                "align": True,
                "diarize": False,
            }
        },
        "large-v1": {
            "legacy_large_v1_uk": {
                "description": "Повна транскрипція (large-v1) + діаризація",
                "language": "uk",
                "clean_mode": "custom",
                "clean_dir": "./clean",
                "post_action": "keep",
                "align": True,
                "diarize": True,
            },
            "legacy_large_v1_en": {
                "description": "Full transcription (large-v1) + diarization",
                "language": "en",
                "clean_mode": "custom",
                "clean_dir": "./clean",
                "post_action": "keep",
                "align": True,
                "diarize": True,
            },
        },
        "large-v2": {
            "legacy_large_v2_uk": {
                "description": "Повна транскрипція (large-v2) + діаризація",
                "language": "uk",
                "clean_mode": "custom",
                "clean_dir": "./clean",
                "post_action": "keep",
                "align": True,
                "diarize": True,
            },
            "legacy_large_v2_en": {
                "description": "Full transcription (large-v2) + diarization",
                "language": "en",
                "clean_mode": "custom",
                "clean_dir": "./clean",
                "post_action": "keep",
                "align": True,
                "diarize": True,
            },
        },
        "large": {
            "legacy_large_uk": {
                "description": "Повна транскрипція (large) + діаризація",
                "language": "uk",
                "clean_mode": "custom",
                "clean_dir": "./clean",
                "post_action": "keep",
                "align": True,
                "diarize": True,
            },
            "legacy_large_en": {
                "description": "Full transcription (large) + diarization",
                "language": "en",
                "clean_mode": "custom",
                "clean_dir": "./clean",
                "post_action": "keep",
                "align": True,
                "diarize": True,
            },
        },
        "large-v3": {
            "full_uk": {
                "description": "Повна транскрипція (large-v3) + діаризація",
                "language": "uk",
                "clean_mode": "custom",
                "clean_dir": "./clean",
                "post_action": "keep",
                "align": True,
                "diarize": True,
            },
            "full_uk_chunked": {
                "description": "Повна (large-v3) + діаризація, з розбиттям на частини",
                "language": "uk",
                "clean_mode": "custom",
                "clean_dir": "./clean",
                "post_action": "keep",
                "align": True,
                "diarize": True,
                "chunk_minutes": 10,
                "max_workers": 2,
            },
            "full_en": {
                "description": "Full transcription (large-v3) + diarization",
                "language": "en",
                "clean_mode": "custom",
                "clean_dir": "./clean",
                "post_action": "keep",
                "align": True,
                "diarize": True,
            },
        },
        "distil-large-v2": {
            "distil_v2_uk": {
                "description": "Швидка транскрипція (distil-large-v2) + діаризація",
                "language": "uk",
                "clean_mode": "custom",
                "clean_dir": "./clean",
                "post_action": "keep",
                "align": True,
                "diarize": True,
            },
            "distil_v2_uk_chunked": {
                "description": "Швидка (distil-large-v2) + діаризація, з розбиттям на частини",
                "language": "uk",
                "clean_mode": "custom",
                "clean_dir": "./clean",
                "post_action": "keep",
                "align": True,
                "diarize": True,
                "chunk_minutes": 10,
                "max_workers": 2,
            },
        },
        "distil-large-v3": {
            "distil_v3_uk": {
                "description": "Швидка транскрипція (distil-large-v3) + діаризація",
                "language": "uk",
                "clean_mode": "custom",
                "clean_dir": "./clean",
                "post_action": "keep",
                "align": True,
                "diarize": True,
            },
            "distil_v3_uk_chunked": {
                "description": "Швидка (distil-large-v3) + діаризація, з розбиттям на частини",
                "language": "uk",
                "clean_mode": "custom",
                "clean_dir": "./clean",
                "post_action": "keep",
                "align": True,
                "diarize": True,
                "chunk_minutes": 10,
                "max_workers": 2,
            },
        },
        "distil-large-v3.5": {
            "distil_v35_uk": {
                "description": "Швидка транскрипція (distil-large-v3.5) + діаризація",
                "language": "uk",
                "clean_mode": "custom",
                "clean_dir": "./clean",
                "post_action": "keep",
                "align": True,
                "diarize": True,
            },
            "distil_v35_uk_chunked": {
                "description": "Швидка (distil-large-v3.5) + діаризація, з розбиттям на частини",
                "language": "uk",
                "clean_mode": "custom",
                "clean_dir": "./clean",
                "post_action": "keep",
                "align": True,
                "diarize": True,
                "chunk_minutes": 10,
                "max_workers": 2,
            },
        },
        "large-v3-turbo": {
            "turbo_uk": {
                "description": "Дуже швидка транскрипція (large-v3-turbo) + діаризація",
                "language": "uk",
                "clean_mode": "custom",
                "clean_dir": "./clean",
                "post_action": "keep",
                "align": True,
                "diarize": True,
            },
            "turbo_uk_chunked": {
                "description": "Дуже швидка (large-v3-turbo) + діаризація, з розбиттям на частини",
                "language": "uk",
                "clean_mode": "custom",
                "clean_dir": "./clean",
                "post_action": "keep",
                "align": True,
                "diarize": True,
                "chunk_minutes": 10,
                "max_workers": 2,
            },
            "turbo_en": {
                "description": "Fast full transcription (large-v3-turbo) + diarization",
                "language": "en",
                "clean_mode": "custom",
                "clean_dir": "./clean",
                "post_action": "keep",
                "align": True,
                "diarize": True,
            },
        },
        "turbo": {
            "turbo_alt_uk": {
                "description": "Дуже швидка транскрипція (turbo) + діаризація",
                "language": "uk",
                "clean_mode": "custom",
                "clean_dir": "./clean",
                "post_action": "keep",
                "align": True,
                "diarize": True,
            },
            "turbo_alt_uk_chunked": {
                "description": "Дуже швидка (turbo) + діаризація, з розбиттям на частини",
                "language": "uk",
                "clean_mode": "custom",
                "clean_dir": "./clean",
                "post_action": "keep",
                "align": True,
                "diarize": True,
                "chunk_minutes": 10,
                "max_workers": 2,
            },
        },
    },
    "realtime": {
        "tiny": {
            "realtime_mono": {
                "description": "Реальний час, тільки мікрофон",
                "language": "uk",
                "chunk_duration": 3,
                "record_both": False,
                "save_audio": True,
            }
        },
        "base": {
            "realtime_dual": {
                "description": "Реальний час, мікрофон + динаміки",
                "language": "uk",
                "chunk_duration": 5,
                "record_both": True,
                "save_audio": True,
            }
        },
    },
}


def profiles_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "profiles.yaml")


def _try_load_yaml(path: str) -> dict | None:
    if yaml is None or not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else None


def _ensure_user_profiles():
    if os.path.exists(USER_PROFILES_PATH):
        return
    os.makedirs(os.path.dirname(USER_PROFILES_PATH), exist_ok=True)
    if yaml is not None:
        with open(USER_PROFILES_PATH, "w", encoding="utf-8") as f:
            yaml.dump(EMBEDDED_PROFILES, f, allow_unicode=True, default_flow_style=False)
    else:
        import json
        with open(USER_PROFILES_PATH, "w", encoding="utf-8") as f:
            json.dump(EMBEDDED_PROFILES, f, ensure_ascii=False, indent=2)


def load_profiles() -> dict:
    _ensure_user_profiles()

    data = _try_load_yaml(USER_PROFILES_PATH)
    if data is not None:
        return data

    dev_path = profiles_path()
    if dev_path != USER_PROFILES_PATH:
        data = _try_load_yaml(dev_path)
        if data is not None:
            return data

    return EMBEDDED_PROFILES


def list_models(mode: str | None = None) -> list[str]:
    profiles = load_profiles()
    models = set()
    for profile_mode, models_dict in profiles.items():
        if mode and profile_mode != mode:
            continue
        models.update(models_dict.keys())
    return sorted(models)


def list_profiles(mode: str | None = None, model: str | None = None) -> list[tuple[str, dict]]:
    profiles = load_profiles()
    result = []
    for profile_mode, models_dict in profiles.items():
        if mode and profile_mode != mode:
            continue
        for profile_model, profile_list in models_dict.items():
            if model and profile_model != model:
                continue
            for name, cfg in profile_list.items():
                enriched = dict(cfg)
                enriched["mode"] = profile_mode
                enriched["model"] = profile_model
                result.append((name, enriched))
    return result


def get_profile(name: str) -> dict | None:
    profiles = load_profiles()
    for models_dict in profiles.values():
        for profile_list in models_dict.values():
            if name in profile_list:
                cfg = dict(profile_list[name])
                return cfg
    return None
