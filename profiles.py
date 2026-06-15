import os
import yaml


def profiles_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "profiles.yaml")


def load_profiles() -> dict:
    path = profiles_path()
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


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
