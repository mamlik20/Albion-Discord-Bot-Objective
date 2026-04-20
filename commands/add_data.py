# commands/add_data.py

import discord
from datetime import datetime, timedelta, timezone
from discord import app_commands
from utils.data_store import data_lock, save_data, load_data, load_allowed_roles
from typing import List, Optional
import logging
import re
from commands import show_data as show_data_module
from commands.party_maker import increment_user_stats 

MAINTENANCE_START_UTC = 10  # 10:00 по UTC
MAINTENANCE_DURATION_MINUTES = 5  # Длительность 10 минут

try:
    with open("locations.txt", "r", encoding="utf-8") as f:
        locations = [line.strip() for line in f if line.strip()]
except FileNotFoundError:
    logging.warning("Файл locations.txt не найден. Автозаполнение локаций не будет доступно.")
    locations = []

try:
    with open("object_names.txt", "r", encoding="utf-8") as f:
        object_names_list = [line.strip() for line in f if line.strip()]
except FileNotFoundError:
    logging.warning("Файл object_names.txt не найден. Автозаполнение названий объектов не будет доступно.")
    object_names_list = []


async def _internal_add_item(
        interaction: discord.Interaction,
        time_str: str,
        location: str,
        object_name: str
) -> Optional[str]:
    """
    Внутренняя логика добавления объекта. Используется командами /add_data и /add_from_image.
    Возвращает строку с ошибкой или None в случае успеха.
    """
    guild_id = interaction.guild_id
    user_selected_location = location.strip()
    user_selected_object_name = object_name.strip()

    allowed_role_ids = load_allowed_roles(guild_id)
    if allowed_role_ids:
        user_role_ids = [role.id for role in interaction.user.roles]
        if not any(role_id in allowed_role_ids for role_id in user_role_ids):
            return "У вас нет прав для добавления данных."

    try:
        hours = 0
        minutes = 0

        processed_time_str = time_str.lower().replace(' ', '')

        hours_match = re.search(r'(\d+)[чh]', processed_time_str)
        if hours_match:
            hours = int(hours_match.group(1))

        minutes_match = re.search(r'(\d+)[мm]', processed_time_str)
        if minutes_match:
            minutes = int(minutes_match.group(1))

        if not hours_match and not minutes_match and ':' in processed_time_str:
            parts = processed_time_str.split(':')
            if len(parts) == 2:
                hours = int(parts[0])
                minutes = int(parts[1])
            else:
                raise ValueError("Неверный формат ЧЧ:ММ")
        elif not hours_match and not minutes_match:
            if processed_time_str.isdigit():
                minutes = int(processed_time_str)
            else:
                raise ValueError("Нераспознанный формат времени")

        if hours < 0 or minutes < 0 or minutes >= 60:
            raise ValueError("Некорректное значение часов или минут.")
        if hours == 0 and minutes == 0:
            return "Время жизни объекта должно быть больше нуля."


        now_utc = datetime.now(timezone.utc)
        time_delta = timedelta(hours=hours, minutes=minutes)
        expiration_time_utc = now_utc + time_delta

        applied_correction = False

        maint_today_start = now_utc.replace(hour=MAINTENANCE_START_UTC, minute=0, second=0, microsecond=0)
        maint_today_end = maint_today_start + timedelta(minutes=MAINTENANCE_DURATION_MINUTES)

        if (now_utc < maint_today_end) and (maint_today_start < expiration_time_utc):
            applied_correction = True

        if not applied_correction:
            tomorrow_utc = now_utc + timedelta(days=1)
            maint_tomorrow_start = tomorrow_utc.replace(hour=MAINTENANCE_START_UTC, minute=0, second=0, microsecond=0)
            maint_tomorrow_end = maint_tomorrow_start + timedelta(minutes=MAINTENANCE_DURATION_MINUTES)

            # Проверяем пересечение с завтрашним интервалом
            if (now_utc < maint_tomorrow_end) and (maint_tomorrow_start < expiration_time_utc):
                applied_correction = True

        if applied_correction:
            expiration_time_utc += timedelta(minutes=MAINTENANCE_DURATION_MINUTES)
            logging.info(
                f"Применена корректировка на техобслуживание (+{MAINTENANCE_DURATION_MINUTES} мин) для объекта '{object_name}'")

        time_unix = int(expiration_time_utc.timestamp())

    except (ValueError, TypeError):
        return f"Ошибка: Некорректный формат времени. Используйте форматы: `1ч 30м`, `2ч`, `45м`, `1:30`, `45`."

    if not user_selected_location or not user_selected_object_name:
        return "Ошибка: Локация и название объекта не могут быть пустыми."

    async with data_lock:
        current_data_store = load_data(guild_id)
        items = current_data_store.get("items", [])

        existing_items = [
            item for item in items 
            if item.get("location", "").lower() == user_selected_location.lower() and \
               item.get("object_name", "").lower() == user_selected_object_name.lower()
        ]

        for item in existing_items:
            existing_time = item.get("time", 0)
            time_diff = abs(existing_time - time_unix)
            if time_diff < 300:  # 5 минут
                return f"Ошибка: Объект **{user_selected_object_name}** в локации **{user_selected_location}** с похожим временем уже существует."

        new_item = {
            "time": time_unix,
            "location": user_selected_location,
            "object_name": user_selected_object_name,
            "added_by_id": interaction.user.id,
            "added_by_name": str(interaction.user)
        }
        items.append(new_item)
        
        save_data(
            guild_id, 
            items, 
            current_data_store.get("allowed_roles", []), 
            current_data_store.get("party_admin_roles", [])
        )
        
        increment_user_stats(interaction.user.id, guild_id, str(interaction.user))
        # -------------------------------

        logging.info(f"Объект '{user_selected_object_name}' в локации '{user_selected_location}' добавлен пользователем {interaction.user} (ID: {interaction.user.id}).")

    if interaction.channel and isinstance(interaction.channel, discord.TextChannel):
        await show_data_module.update_show_data_message_for_channel(interaction.client, guild_id,
                                                                    interaction.channel.id)

    return None

@app_commands.command(name="add_data", description="Добавляет данные о местоположении объекта")
@app_commands.describe(
    time_str="Время жизни (напр. '1ч 30м', '45м', '1:30', '45')",
    location="Выберите или введите локацию",
    object_name="Выберите или введите название объекта"
)
async def add_data(interaction: discord.Interaction, time_str: str, location: str, object_name: str):
    """Команда для ручного добавления объекта."""
    await interaction.response.defer(thinking=True, ephemeral=True)
    error_message = await _internal_add_item(interaction, time_str, location, object_name)
    if error_message:
        await interaction.followup.send(error_message, ephemeral=True)
    else:
        await interaction.followup.send(
            f"Объект **{object_name}** в локации **{location}** успешно добавлен.",
            ephemeral=True
        )


@add_data.autocomplete("location")
async def location_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    if not locations: return []
    current_lower = current.lower()
    choices = [
        app_commands.Choice(name=loc, value=loc)
        for loc in locations
        if current_lower in loc.lower()
    ]
    choices.sort(key=lambda c: (not c.name.lower().startswith(current_lower), c.name.lower()))
    return choices[:25]


@add_data.autocomplete("object_name")
async def object_name_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    if not object_names_list: return []
    current_lower = current.lower()
    choices = [
        app_commands.Choice(name=name, value=name)
        for name in object_names_list
        if current_lower in name.lower()
    ]
    choices.sort(key=lambda c: (not c.name.lower().startswith(current_lower), c.name.lower()))
    return choices[:25]