# tasks/cleanup_data.py
import time
import logging
import discord
import os
from utils.data_store import data_lock, save_data, load_data, show_data_messages
from commands import show_data as show_data_module

SIGNALS_DIR = "bot_signals"
os.makedirs(SIGNALS_DIR, exist_ok=True)


async def cleanup_data(bot: discord.Client):

    guilds_to_update_by_signal = set()
    try:
        for filename in os.listdir(SIGNALS_DIR):
            if filename.startswith("update_signal_") and filename.endswith(".txt"):
                try:
                    guild_id_str = filename.replace("update_signal_", "").replace(".txt", "")
                    guild_id = int(guild_id_str)
                    guilds_to_update_by_signal.add(guild_id)
                    os.remove(os.path.join(SIGNALS_DIR, filename))
                    logging.info(f"Найден и удален сигнальный файл для сервера {guild_id}.")
                except (ValueError, OSError) as e:
                    logging.error(f"Ошибка при обработке сигнального файла {filename}: {e}")
    except Exception as e:
        logging.error(f"Ошибка при чтении папки с сигналами: {e}")

    any_changes_made = False

    for guild in bot.guilds:
        guild_id = guild.id
        items_changed_for_guild = False

        if guild_id in guilds_to_update_by_signal:
            items_changed_for_guild = True
            logging.info(f"Принудительное обновление для сервера {guild.name} ({guild_id}) по сигналу с сайта.")

        async with data_lock:
            current_data_store = load_data(guild_id)
            if not isinstance(current_data_store, dict) or "items" not in current_data_store:
                continue

            items = current_data_store.get("items", [])
            allowed_roles_for_guild = current_data_store.get("allowed_roles", [])
            now_timestamp = int(time.time())

            original_item_count = len(items)
            items_to_keep = [item for item in items if isinstance(item, dict) and item.get('time', 0) > now_timestamp]

            if len(items_to_keep) < original_item_count:
                items_changed_for_guild = True
                any_changes_made = True
                save_data(guild_id, items_to_keep, allowed_roles_for_guild)
                logging.info(
                    f"На сервере {guild.name} ({guild_id}) удалено {original_item_count - len(items_to_keep)} истекших объектов.")

        if items_changed_for_guild:
            active_channels_on_guild = [
                ch_id for ch_id in show_data_messages if
                bot.get_channel(ch_id) and bot.get_channel(ch_id).guild.id == guild_id
            ]
            for channel_id in active_channels_on_guild:
                try:
                    await show_data_module.update_show_data_message_for_channel(bot, guild_id, channel_id)
                except Exception as e:
                    logging.error(f"Ошибка при обновлении show_data в cleanup для канала {channel_id}: {e}")

    if any_changes_made:
        logging.info("Задача cleanup_data завершена с изменениями.")

    # Или можно сделать более компактный лог:
    # logging.debug("Задача cleanup_data завершена.")  # debug вместо info