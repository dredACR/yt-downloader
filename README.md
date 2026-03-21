# YT Downloader

Веб-сервіс для завантаження відео з YouTube.

## Встановлення

### 1. Клонуйте / розпакуйте проект

```bash
cd yt-downloader
```

### 2. Створіть віртуальне середовище (рекомендовано)

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Встановіть залежності

```bash
pip install -r requirements.txt
```

> **Примітка:** Для злиття відео та аудіо потрібен **FFmpeg**.
> - Windows: https://ffmpeg.org/download.html → додайте у PATH
> - macOS: `brew install ffmpeg`
> - Ubuntu/Debian: `sudo apt install ffmpeg`

### 4. Запустіть сервер

```bash
python app.py
```

### 5. Відкрийте браузер

```
http://localhost:5000
```

## Використання

1. Вставте посилання на YouTube відео
2. Натисніть **АНАЛІЗ** — побачите назву та мініатюру
3. Оберіть якість (або MP3 для аудіо)
4. Натисніть **ЗАВАНТАЖИТИ**
5. Після завантаження натисніть **ЗБЕРЕГТИ**

## Структура проекту

```
yt-downloader/
├── app.py              # Flask сервер
├── requirements.txt    # Python залежності
├── templates/
│   └── index.html      # Веб-інтерфейс
└── downloads/          # Тимчасові файли (створюється автоматично)
```
