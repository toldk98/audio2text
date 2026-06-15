# Ідеї на майбутнє

## 1. Логування замість print()
- Зараз весь вивід через `print()`
- Перейти на `logging` з рівнями: INFO, DEBUG, WARNING, ERROR
- Додати файловий лог з ротацією
- Зберегти вивід у термінал через `StreamHandler`

## 2. Batch mode — обробити всі файли з ./Audio/
- Один запуск → всі `.m4a`/`.wav`/`.mp3` по черзі з одним профілем
- Для нічної пачки або масової обробки
- `python main.py batch --profile full_uk_chunked`

## 3. Оптимізація часу
Поточна швидкість для 2h файлу на CPU (distil-large-v3, 2 workers): ~90 хв
Ціль: зменшити до ~35-40 хв

### 3.1 Вимкнути діаризацію, якщо спікери не потрібні
- Pyannote на CPU: ~20-25 хв
- Профіль `*_uk` без diarize: `diarize: false`

### 3.2 Полегшити clean audio
- `afftdn,loudnorm` — ~12 хв, найважчий ffmpeg фільтр
- Для чистого аудіо: вимкнути повністю (`clean_mode: temp` без ефекту)
- Або замінити на `highpass=f=200,lowpass=f=3000` (~2 хв)

### 3.3 Більше workers
- 2 workers → 14 chunks / 2 = 7 раундів
- 4 workers → 14 / 4 = 4 раунди (економія ~21 хв на transcribe)
- Обмеження: CPU multithreading, RAM

### 3.4 Вимкнути align
- wav2vec2 align на CPU: ~12 хв
- Якщо текст без таймкодів влаштовує — `align: false`
