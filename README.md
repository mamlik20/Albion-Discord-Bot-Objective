# Albion Discord Bot Objective

Discord-бот для отслеживания игровых объектов (ресурсы, вихри, сферы) с веб-панелью управления.

## Возможности

**Discord-команды:**
- `/add_data` — добавить объект вручную (локация, название, время жизни)
- `/add_from_image` — распознать объект с скриншота через Google Gemini AI
- `/show_data` — показать список активных объектов в виде embed-сообщения
- `/delete_data` — удалить объект из списка
- `/set_allowed_roles` — настроить роли, которым разрешено добавлять/удалять объекты
- `/game` — запустить сбор пачек (Party Maker) по шаблону
- `/setup_create`, `/setup_delete`, `/setup_list` — управление шаблонами пачек

**Автоматика:**
- Автоудаление истёкших объектов каждую минуту
- Автокоррекция времени при пересечении с техобслуживанием сервера (10:00 UTC)
- Автообновление embed-сообщения `/show_data` при любых изменениях
- Защита от дублей при добавлении объектов

**Веб-панель** (Flask, порт 5000):
- Просмотр, редактирование и удаление объектов по серверам
- Управление шаблонами Party Maker
- Редактирование списков локаций, объектов, аббревиатур и иконок
- Статистика добавлений по пользователям
- Ролевая система доступа: `admin`, `editor`, `party_manager`

## Стек

- Python 3.11
- discord.py
- Google Gemini API (`google-generativeai`)
- Flask + Flask-Login
- SQLite
- Docker

## Быстрый старт

### 1. Клонировать репозиторий

```bash
git clone https://github.com/mamlik20/Albion-Discord-Bot-Objective.git
cd Albion-Discord-Bot-Objective
```

### 2. Изменить `.env` файл

```env
DISCORD_BOT_TOKEN=Сюда_токен_бота
GOOGLE_API_KEY=Сюда_ключи_через_запятую
```

### 3. Настроить списки

- `locations.txt` — список локаций (по одной на строку)
- `object_names.txt` — список названий объектов (по одной на строку)
- `icons.json` — маппинг ключевых слов → эмодзи
- `abbreviations.json` — маппинг полных названий → сокращений

### 4. Запустить через Docker Compose

```bash
docker compose up -d --build
```

Бот запустится на фоне, веб-панель будет доступна на `http://localhost:5000`.

## Структура проекта

```
├── main.py                  # Точка входа, настройка бота
├── commands/
│   ├── add_data.py          # /add_data
│   ├── add_from_image.py    # /add_from_image
│   ├── show_data.py         # /show_data
│   ├── delete_data.py       # /delete_data
│   ├── set_allowed_roles.py # /set_allowed_roles
│   └── party_maker.py       # /game, /setup_*
├── tasks/
│   └── cleanup_data.py      # Фоновая очистка истёкших объектов
├── utils/
│   ├── data_store.py        # Работа с JSON-данными серверов
│   └── gemini_manager.py    # Менеджер ключей Gemini API
├── website/
│   └── app.py               # Flask веб-панель
├── bot_data/                # Данные серверов (JSON + SQLite)
├── bot_signals/             # Сигналы обновления от веб-панели к боту
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## Веб-панель

По умолчанию доступны три учётные записи (настраиваются в `website/app.py`):

| Логин  | Пароль | Роль            | Доступ                          |
|--------|--------|------------------|---------------------------------|
| admin  | admin  | Администратор    | Всё                             |
| scout  | 123    | Редактор         | Просмотр и редактирование объектов |
| rl     | 123    | Party Manager    | Управление пачками              |

> Смените пароли и `secret_key` перед деплоем в продакшн.

## Логи

Все события пишутся в `bot.log` и дублируются в stdout (видно через `docker compose logs`).
