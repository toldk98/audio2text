MODEL_SIZES_MB = {
    "tiny": 150,
    "base": 300,
    "small": 500,
    "medium": 1500,
    "large-v1": 3000,
    "large-v2": 3000,
    "large-v3": 3000,
    "large": 3000,
    "distil-large-v2": 1500,
    "distil-large-v3": 1500,
    "distil-large-v3.5": 1500,
    "large-v3-turbo": 3000,
    "turbo": 3000,
}
model_name_list = list(MODEL_SIZES_MB.keys())

language_list = [
    "uk",
    "en",
    "pl",
    "de",
    "fr",
    "es",
    "it",
    "pt",
    "nl",
    "ja",
    "zh",
    "ko",
    "ar",
    "tr",
]

chunk_options = [0, 5, 10, 15, 20, 30]

cpu_levels = [
    "high",
    "medium",
    "low",
]
