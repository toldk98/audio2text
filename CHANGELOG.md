# CHANGELOG

## v0.2.0 (2026-06-16)

### GUI
- Додано вкладку **Налаштування**: тема, авто-завантаження, профілі, реєстр файлів, кеш моделей
- Додано **редагування профілів** — додавати, редагувати, видаляти через діалог
- Додано **керування реєстром файлів** — вибір збережених файлів, додавання, видалення, очищення битих
- Додано **керування кешем моделей** — Treeview з розміром/типом/датою, видалення
- Додано **вибір теми** (ttkbootstrap) з persistence у `settings.json`
- Додано **ToolTip** — підказки при наведенні на поля
- Виправлено: `LabelFrame` більше не використовує `padding=`
- Виправлено: `whisper_offline` імпортується лазіво — GUI не падає без whisperx

### Завантаження моделей
- `allow_download` параметр замість `input()` — GUI не блокується
- Чекбокс «Авто-завантаження моделей» в GUI
- CLI: `-y` / `--yes` для тихого режиму
- Статус моделі в редакторі профілів (розмір або ⚡ якщо не закешовано)

### Сумісність
- Зафіксовано `torch==2.3.0` та `torchaudio==2.3.0` у `requirements.txt`
- Виправлено `libctranslate2` executable stack (ELF patching)

### Інше
- README.md з документацією
- `save_settings()` / `load_settings()` у token_manager.py
- `upsert_profile()` / `delete_profile()` у profiles.py
- Cleaned audio та post_action тепер керуються через WorkDir

## v0.1.1 (2026-06-15)

- `profiles.yaml` копіюється в `~/.config/audio2text/` при першому запуску
- Вбудовані профілі в Python (EMBEDDED_PROFILES), YAML — для користувацьких змін
- Замінено `__file__` шляхи на `platformdirs` (PyInstaller сумісність)

## v0.1.0 (2026-06-14)

- Базовий CLI: `python main.py file <path>` та `python main.py pick`
- WhisperX транскрипція (CTranslate2)
- Вирівнювання (align) через wav2vec2
- Діаризація через pyannote.audio
- Розбиття на частини з паралельною обробкою
- Resume — продовження перерваної транскрипції
- WorkDir — централізоване керування тимчасовими файлами
- Зовнішній реєстр файлів (JSON)
- Fzf + fallback `_simple_choice()`
- Перша версія GUI (ttkbootstrap): транскрипція + лог
- Керування HF токеном (keychain / файл / питати)
