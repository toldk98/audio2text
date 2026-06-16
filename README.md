# Audio2Text

Транскрибація аудіо в текст з використанням WhisperX, вирівнюванням (align) та діаризацією (розпізнаванням спікерів).

## Можливості

- **WhisperX** — швидка транскрипція з CTranslate2
- **Вирівнювання (align)** — точні таймкоди через wav2vec2
- **Діаризація** — хто і коли говорить (pyannote.audio)
- **Розбиття на частини** — паралельна обробка довгих файлів
- **Resume** — перервану транскрипцію можна продовжити
- **GUI** — графічний інтерфейс (ttkbootstrap)
- **CLI** — командний рядок
- **Profiles** — збережені набори налаштувань (YAML)
- **Реєстр файлів** — швидкий доступ до зовнішніх аудіофайлів
- **Керування кешем** — перегляд/видалення закешованих моделей

## Встановлення

```bash
# Python 3.10+
python -m venv venv
source venv/bin/activate

# Встановити залежності
pip install -r requirements.txt

# Або вручну:
pip install torch==2.3.0 torchaudio==2.3.0 --index-url https://download.pytorch.org/whl/cpu
pip install whisperx ttkbootstrap platformdirs pyyaml python-dotenv sounddevice
```

> **Важливо:** Використовуйте саме `torch==2.3.0` / `torchaudio==2.3.0` — новіші версії несумісні з whisperx.

## Використання

### GUI

```bash
python main.py
```

Вкладки:

- **Транскрипція** — вибір файлу, токен, профіль, запуск + лог
- **Лог** — прогрес і вивід транскрипції
- **Налаштування** — тема, авто-завантаження моделей, профілі, реєстр файлів, кеш моделей

### CLI

```bash
# Транскрибувати файл
python main.py file шлях/до/аудіо.m4a

# З вибором профілю та моделі
python main.py file audio.m4a --model_name large-v3 --language uk

# Розбити на частини для паралельної обробки
python main.py file audio.m4a --chunk_minutes 10 --max_workers 4

# Без запиту підтвердження завантаження моделей
python main.py file audio.m4a -y

# Інтерактивний вибір
python main.py pick
```

### Профілі

Профілі зберігаються в `~/.config/audio2text/profiles.yaml`.
Вбудовані профілі копіюються туди при першому запуску.

Приклад профілю:

```yaml
file:
  large-v3:
    full_uk:
      description: "Повна транскрипція (large-v3) + діаризація"
      language: uk
      align: true
      diarize: true
```

**Поля профілю:**

| Поле            | Тип  | Опис                               |
|-----------------|------|------------------------------------|
| `description`   | str  | Опис (показується в GUI)           |
| `language`      | str  | Код мови (uk, en, pl, …)           |
| `align`         | bool | Вирівнювання таймкодів             |
| `diarize`       | bool | Розпізнавання спікерів             |
| `model`         | str  | Розмір моделі (large-v3, base, …)  |
| `chunk_minutes` | int  | Розбиття на частини (0 = вимкнено) |
| `max_workers`   | int  | Потоків для паралельної обробки    |

### HuggingFace Token

Для діаризації потрібен токен HuggingFace:

1. Зареєструйтесь на [huggingface.co](https://huggingface.co)
2. Прийміть умови моделі: [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
3. Створіть токен: [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)

Токен можна зберегти через GUI або встановити змінну `HF_TOKEN` у `.env`.

### Реєстр зовнішніх файлів

Файли, що лежать поза `Audio/`, можна додати до реєстру — вони з'являться в списку
для швидкого вибору (GUI: комбобокс на вкладці транскрипції; CLI: `python main.py pick`).

Реєстр зберігається в `~/.local/share/audio2text/external_registry.json`.

## Структура директорій

```
~/.cache/audio2text/          # Робочі директорії транскрипцій
~/.cache/whisper/             # Кеш моделей Whisper (.pt)
~/.cache/huggingface/hub/     # Кеш CTranslate2/HF моделей
~/.config/audio2text/         # Налаштування
  ├── profiles.yaml           # Профілі транскрипції
  ├── settings.json           # Токен, тема
  └── token_storage_mode.txt  # Режим збереження токена
~/.local/share/audio2text/    # Дані
  ├── Audio/                  # Аудіофайли за замовчуванням
  └── external_registry.json  # Реєстр зовнішніх файлів
```

## Подяки

- [WhisperX](https://github.com/m-bain/whisperX) — транскрипція + align + діаризація
- [pyannote.audio](https://github.com/pyannote/pyannote-audio) — діаризація
- [ttkbootstrap](теhttps://github.com/israel-dryer/ttkbootstrap) — GUI тема
