# Audio2Text

[![Release](https://img.shields.io/github/v/release/toldk98/audio2text)](https://github.com/toldk98/audio2text/releases)
[![License](https://img.shields.io/github/license/toldk98/audio2text)](LICENSE)
[![CI](https://github.com/toldk98/audio2text/actions/workflows/build.yml/badge.svg)](https://github.com/toldk98/audio2text/actions)

> 💡 **Not Ukrainian?** See [English README](README_EN.md).

Транскрибація аудіо в текст з використанням WhisperX, вирівнюванням (align) та діаризацією (розпізнаванням спікерів). Працює на CPU та NVIDIA GPU.

## Можливості

**Транскрипція**
- **WhisperX** — швидка транскрипція з CTranslate2
- **Вирівнювання (align)** — точні таймкоди через wav2vec2
- **Діаризація** — хто і коли говорить (pyannote.audio)
- **Розбиття на частини** — паралельна обробка довгих файлів (10+ годин)
- **Resume** — перервану транскрипцію можна продовжити
- **Фільтр аудіо** — попередня обробка (повний/легкий/вимк.)

**Інтерфейс**
- **GUI** — графічний інтерфейс (ttkbootstrap) з перемиканням мови на льоту
- **CLI** — командний рядок
- **Профілі** — збережені набори налаштувань (YAML), створення/редагування через GUI
- **Реєстр файлів** — швидкий доступ до зовнішніх аудіофайлів

**Безпека та контроль**
- **Контроль CPU** — три рівні навантаження (високий/середній/низький) з автоматичним обмеженням потоків
- **OOM (захист від нестачі RAM) / DISKOM (захист від нестачі місця на диску)** — перевірка перед запуском
- **Токен через system keychain** — безпечне зберігання HuggingFace токена

**Інструменти**
- **Керування кешем** — перегляд/видалення закешованих моделей
- **Формати аудіо:** M4A, MP3, WAV, OGG (усе, що читає ffmpeg)

## Системні вимоги

- **ОС:** Windows 10/11 64-bit, Linux (будь-який дистрибутив)
- **Python:** 3.10–3.12 (для ручного встановлення)
- **RAM:** мінімум 8 GB (рекомендовано 16 GB)
- **Диск:** ~3 GB для моделей + місце для аудіофайлів
- **GPU (опціонально):** NVIDIA з VRAM 6+ GB (CUDA 12.1)

## Встановлення

### Windows ( Portable )

1. Завантажте **Audio2Text-vX.X.X-windows.zip** з [Releases](https://github.com/toldk98/audio2text/releases)
2. Розпакуйте в будь-яку папку (наприклад `C:\Audio2Text`)
3. Запустіть `install.ps1`:
   - **Не двічі клікайте файл** — він відкриється в блокноті, а не запуститься.
   - Натисніть `Win+R`, введіть `powershell`, натисніть Enter. У вікні PowerShell перейдіть до папки розпакування (`cd C:\Audio2Text`) і виконайте:
     ```
     powershell -ExecutionPolicy Bypass -File install.ps1
     ```
   - Або правою кнопкою миші → "Run with PowerShell" (якщо доступно).
4. Після встановлення запускайте Audio2Text через меню **Пуск** або `audio2text.bat`.

> Якщо ярлик у Пуск не створився — запускайте напряму `audio2text.bat` з папки розпакування.

> Якщо програма не запускається — запустіть `audio2text.bat` вручну в терміналі та скопіюйте текст помилки.

> **Windows Defender / SmartScreen:** при завантаженні та запуску може з'явитися попередження "Windows захистила ваш ПК". Натисніть **"Докладніше"** → **"Виконати все одно"**. Це стандартне попередження для непідписаних застосунків.

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

# Системні залежності (Linux)
sudo apt install ffmpeg   # або dnf install ffmpeg / pacman -S ffmpeg

# Залежності Python
pip install torch==2.3.0 torchaudio==2.3.0 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

> **Важливо:** torch має бути саме `2.3.0`. Новіші версії несумісні з whisperx.

> **GPU:** якщо у вас NVIDIA GPU з CUDA 12.1, замініть `--index-url .../whl/cpu` на `--index-url https://download.pytorch.org/whl/cu121`.

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

![Головне вікно](screenshots/main.png)
*Головне вікно: вибір файлу, профіль, запуск транскрипції*

![Редактор профілю](screenshots/profiles.png)
*Створення профілю транскрипції*

![Налаштування](screenshots/settings.png)
*Налаштування: тема, мова*

![Керування моделями](screenshots/models.png)
*Авто-завантаження та кеш моделей*

Вкладки:
- **Транскрипція** — вибір файлу, токен, профіль, CPU load, запуск + лог
- **Лог** — прогрес і вивід транскрипції
- **Налаштування** — підвкладки:
  - **Загальні** — тема оформлення, мова інтерфейсу (UK/EN)
  - **Профілі** — створення/редагування/видалення профілів
  - **Моделі** — авто-завантаження моделей, керування кешем
  - **Файли** — реєстр зовнішніх аудіофайлів

Результат зберігається у `~/.cache/audio2text/` у вигляді текстового файлу (`.txt`) з розпізнаним текстом, таймкодами та позначками спікерів (якщо діаризація увімкнена).

### CLI

CLI використовує той самий механізм токена, що й GUI: спочатку `HF_TOKEN` з оточення, потім system keychain.

```bash
# Транскрибувати файл
python main.py file шлях/до/аудіо.m4a

# З профілем
python main.py file audio.m4a --profile full_uk

# З вибором моделі та мови
python main.py file audio.m4a --model_name large-v3 --language uk

# Розбити на частини для паралельної обробки
python main.py file audio.m4a --chunk_minutes 10 --max_workers 4

# Без запиту підтвердження завантаження моделей
python main.py file audio.m4a -y

# З прогрес-баром
python main.py file audio.m4a --progress

# Керування вирівнюванням та діаризацією
python main.py file audio.m4a --no-align --diarize

# Фільтр аудіо та навантаження CPU
python main.py file audio.m4a --clean_filter light --max_workers 2

# Інтерактивний вибір
python main.py pick

# Керування кешем моделей
python main.py --list-models
python main.py --delete-model large-v3
```

### Профілі

Профілі зберігаються в `~/.config/audio2text/profiles.yaml`.
Вбудовані профілі копіюються туди при першому запуску.

Профілі можна створювати та редагувати через GUI (Налаштування → Профілі → кнопка Додати/Редагувати).
У CLI профіль застосовується через `--profile <ім'я>` — він заповнює всі параметри, а явні флаги CLI
їх перевизначають.

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

| Поле            | Тип  | Опис                                              |
|-----------------|------|---------------------------------------------------|
| `description`   | str  | Опис (показується в GUI)                          |
| `language`      | str  | Код мови (uk, en, pl, …)                          |
| `align`         | bool | Вирівнювання таймкодів                            |
| `diarize`       | bool | Розпізнавання спікерів                            |
| `model`         | str  | Розмір моделі (large-v3, turbo, distil-*, …)      |
| `clean_filter`  | str  | Фільтр аудіо: full / light / off                  |
| `max_workers`   | int  | Кількість паралельних потоків                     |
| `chunk_minutes` | int  | Розбиття на частини (0 = вимкнено)                |

### HuggingFace Token

Для діаризації потрібен токен HuggingFace:

1. Зареєструйтесь на [huggingface.co](https://huggingface.co)
2. Прийміть умови моделі: [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
3. Створіть токен: [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)

Токен зберігається в **системному сховищі (system keychain)** через `keyring`.
Альтернативно — встановіть змінну середовища `HF_TOKEN`.

#### Налаштування keychain на Linux

Для роботи системного сховища на Linux потрібен `libsecret`:

```bash
# Debian/Ubuntu
sudo apt install libsecret-tools

# Fedora
sudo dnf install libsecret

# Arch Linux
sudo pacman -S libsecret
```

Якщо використовується Wayland або headless-сервер (без графічного сеансу),
додатково встановіть файловий backend:

```bash
pip install keyrings.alt
```

Після цього ключі зберігатимуться у файлі
`~/.local/share/python_keyring/keyrings.alt/file/`.

### Реєстр зовнішніх файлів

Файли, що лежать поза `Audio/`, можна додати до реєстру — вони з'являться в списку
для швидкого вибору (GUI: комбобокс на вкладці транскрипції; CLI: `python main.py pick`).

Реєстр зберігається в `~/.local/share/audio2text/external_registry.json`.

## Мова інтерфейсу

Інтерфейс підтримує українську та англійську мови (за замовчуванням).
Перемикання: **Налаштування → Загальні → Мова** → обрати мову → **Застосувати**.
Мова змінюється одразу, без перезапуску програми.

### Додати нову мову

Скопіюйте файл локалі (напр. `fr.json`) з вмістом як у `en.json` у теку `gui/locales/`.
Комбобокс підхопить її автоматично після перемикання мови або перезапуску.

Файл має містити ключ `"lang.XX"` з назвою мови для комбобокса та переклади потрібних рядків:

```json
{
  "lang.fr": "Français",
  "tab.transcribe": "Transcription",
  ...
}
```

## Структура директорій

```
~/.cache/audio2text/          # Робочі директорії транскрипцій
~/.cache/whisper/             # Кеш моделей Whisper (.pt)
~/.cache/huggingface/hub/     # Кеш CTranslate2/HF моделей
~/.config/audio2text/         # Налаштування
  ├── profiles.yaml           # Профілі транскрипції
  └── settings.json           # Тема
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
# Для Zsh:
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### USB-мікрофон / пристрої запису (Linux)

```bash
# Перевірити, що вас чути:
arecord -l
# Якщо порожньо — встановіть pavucontrol та налаштуйте вхід:
sudo apt install pavucontrol       # Debian/Ubuntu
sudo dnf install pavucontrol       # Fedora
sudo pacman -S pavucontrol         # Arch
```

### Linux — "No keyring backend available"

```bash
# Встановіть libsecret:
sudo apt install libsecret-tools   # Debian/Ubuntu
sudo dnf install libsecret         # Fedora
sudo pacman -S libsecret           # Arch
# Або файловий backend:
pip install keyrings.alt
```

## Ліцензія

MIT License — див. [LICENSE](LICENSE).

## Подяки

- [WhisperX](https://github.com/m-bain/whisperX) — транскрипція + align + діаризація
- [pyannote.audio](https://github.com/pyannote/pyannote-audio) — діаризація
- [ttkbootstrap](https://github.com/israel-dryer/ttkbootstrap) — GUI тема
