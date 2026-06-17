# Audio2Text

Транскрибація аудіо в текст з використанням WhisperX, вирівнюванням (align) та діаризацією (розпізнаванням спікерів). Працює на CPU та NVIDIA GPU.

## Можливості

- **WhisperX** — швидка транскрипція з CTranslate2
- **Вирівнювання (align)** — точні таймкоди через wav2vec2
- **Діаризація** — хто і коли говорить (pyannote.audio)
- **Розбиття на частини** — паралельна обробка довгих файлів (10+ годин)
- **Resume** — перервану транскрипцію можна продовжити
- **GUI** — графічний інтерфейс (ttkbootstrap)
- **CLI** — командний рядок
- **Profiles** — збережені набори налаштувань (YAML)
- **Реєстр файлів** — швидкий доступ до зовнішніх аудіофайлів
- **Керування кешем** — перегляд/видалення закешованих моделей
- **Контроль CPU** — три рівні навантаження (high/medium/low)
- **OOM захист** — перевірка RAM та диска перед запуском

## Встановлення

### Windows ( Portable )

1. Завантажте **Audio2Text-vX.X.X-windows.zip** з [Releases](https://github.com/toldk98/audio2text/releases)
2. Розпакуйте в будь-яку папку (наприклад `C:\Programs\Audio2Text`)
3. Запустіть `install.ps1` (правою кнопкою → "Run with PowerShell" або у терміналі виконайте `powershell -ExecutionPolicy Bypass -File install.ps1`)
4. Після встановлення запускайте Audio2Text через меню **Пуск** або `audio2text.bat`

> Якщо ярлик у Пуск не створився — запускайте напряму `audio2text.bat` з папки розпакування.

> Якщо програма не запускається — запустіть `audio2text.bat` вручну в терміналі та скопіюйте текст помилки.

### Linux ( Portable )

1. Завантажте **Audio2Text-vX.X.X-linux.tar.gz** з [Releases](https://github.com/toldk98/audio2text/releases)
2. Розпакуйте: `tar -xzf Audio2Text-vX.X.X-linux.tar.gz`
3. Запустіть установку: `cd Audio2Text && bash install.sh`
4. Запускайте через меню додатків або командою `audio2text`

### Python ( Manual, всі ОС )

```bash
# Python 3.10+
git clone https://github.com/toldk98/audio2text
cd Audio2Text

# Віртуальне середовище
python -m venv venv
source venv/bin/activate   # Linux/macOS
# .\venv\Scripts\activate  # Windows

# Залежності
pip install torch==2.3.0 torchaudio==2.3.0 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

> **Важливо:** torch має бути саме `2.3.0`. Новіші версії несумісні з whisperx.

Запуск:

```bash
python main.py         # GUI
python main.py file audio.m4a  # CLI
```

## Використання

### GUI
```bash
python main.py
```

Вкладки:
- **Транскрипція** — вибір файлу, токен, профіль, CPU load, запуск + лог
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
| `cpu_profile`   | str  | Рівень CPU: high / medium / low    |

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

## Вирішення проблем

### Windows — програма закривається одразу після запуску

1. Відкрийте **Командний рядок** (`cmd.exe`)
2. Перейдіть у папку з Audio2Text: `cd C:\шлях\до\Audio2Text`
3. Запустіть вручну: `audio2text.bat`
4. Скопіюйте текст помилки та створіть [issue](https://github.com/toldk98/audio2text/issues)

### Linux — "command not found: audio2text"

```bash
# Додати ~/.local/bin до PATH:
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### USB-мікрофон / пристрої запису (Linux)

```bash
# Перевірити, що вас чути:
arecord -l
# Якщо порожньо — встановіть pavucontrol та налаштуйте вхід:
sudo apt install pavucontrol
```

## Подяки

- [WhisperX](https://github.com/m-bain/whisperX) — транскрипція + align + діаризація
- [pyannote.audio](https://github.com/pyannote/pyannote-audio) — діаризація
- [ttkbootstrap](https://github.com/israel-dryer/ttkbootstrap) — GUI тема
