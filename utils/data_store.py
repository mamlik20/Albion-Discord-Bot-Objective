# utils/data_store.py
import asyncio
import json
import os
import logging
from typing import Dict, List, Any

DATA_DIR = "bot_data"
if not os.path.exists(DATA_DIR):
    try:
        os.makedirs(DATA_DIR)
        logging.info(f"Создана директория для данных: {DATA_DIR}")
    except OSError as e:
        logging.error(f"Не удалось создать директорию {DATA_DIR}: {e}")
        DATA_DIR = "."

MESSAGES_FILE_PATH = os.path.join(DATA_DIR, "show_data_messages.json")

def load_show_data_messages() -> Dict[int, int]:
    try:
        with open(MESSAGES_FILE_PATH, "r", encoding="utf-8") as f:
            return {int(k): v for k, v in json.load(f).items()}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_show_data_messages(messages_dict: Dict[int, int]):
    try:
        with open(MESSAGES_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(messages_dict, f, indent=4)
    except IOError as e:
        logging.error(f"Ошибка сохранения сообщений: {e}")

data_lock = asyncio.Lock()
show_data_messages: Dict[int, int] = load_show_data_messages()

def get_data_file_path(guild_id: Any) -> str:
    return os.path.join(DATA_DIR, f"data_{str(guild_id)}.json")

def load_data(guild_id: Any) -> Dict[str, Any]:
    """Загружает данные сервера. Возвращает словарь с дефолтными значениями, если файла нет."""
    data_file = get_data_file_path(guild_id)
    default_structure = {
        "items": [], 
        "allowed_roles": [],
        "party_admin_roles": []
    }
    try:
        with open(data_file, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content: return default_structure
            data = json.loads(content)
            if "allowed_roles" not in data: data["allowed_roles"] = []
            if "party_admin_roles" not in data: data["party_admin_roles"] = []
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        return default_structure
    except Exception as e:
        logging.error(f"Ошибка загрузки данных {data_file}: {e}")
        return default_structure

def save_data(guild_id: Any, items: List[Dict[str, Any]], allowed_roles: List[int], party_admin_roles: List[int] = None):
    data_file = get_data_file_path(guild_id)
    if party_admin_roles is None:
        current = load_data(guild_id)
        party_admin_roles = current.get("party_admin_roles", [])

    data_to_save = {
        "items": items, 
        "allowed_roles": allowed_roles,
        "party_admin_roles": party_admin_roles
    }
    try:
        with open(data_file, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, indent=4)
    except IOError as e:
        logging.error(f"Ошибка сохранения данных {data_file}: {e}")

def load_allowed_roles(guild_id: Any) -> List[int]:
    data = load_data(guild_id)
    return data.get("allowed_roles", [])

def save_allowed_roles(guild_id: Any, allowed_role_ids: List[int]):
    """Обновляет только allowed_roles, не трогая остальное"""
    current_data = load_data(guild_id)
    save_data(guild_id, current_data.get("items", []), allowed_role_ids, current_data.get("party_admin_roles", []))
    logging.info(f"Разрешенные роли для guild {guild_id} обновлены.")

def save_guild_roles_map(guild):
    """Сохраняет имена ролей в файл roles_ID.json для отображения на сайте"""
    roles_map = {str(role.id): role.name for role in guild.roles}
    file_path = os.path.join(DATA_DIR, f"roles_{guild.id}.json")
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(roles_map, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Не удалось сохранить роли сервера {guild.id}: {e}")