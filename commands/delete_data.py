# commands/delete_data.py
import logging
import discord
from discord import app_commands
from utils.data_store import data_lock, save_data, load_data, load_allowed_roles
from typing import List
from commands import show_data as show_data_module

@app_commands.command(name="delete_data", description="Удаляет данные об объекте")
@app_commands.describe(item_to_delete="Выберите объект для удаления")
async def delete_data(interaction: discord.Interaction, item_to_delete: str):
    guild_id = interaction.guild_id
    if not guild_id: return

    allowed_role_ids = load_allowed_roles(guild_id)
    if allowed_role_ids:
        user_role_ids = [role.id for role in interaction.user.roles]
        if not any(role_id in allowed_role_ids for role_id in user_role_ids):
            await interaction.response.send_message("У вас нет прав для удаления данных.", ephemeral=True)
            return

    try:
        if not item_to_delete.startswith("item_"): raise ValueError
        item_index_to_delete = int(item_to_delete.split("_")[1])
    except (ValueError, IndexError):
        await interaction.response.send_message("Некорректный выбор. Используйте автодополнение.", ephemeral=True)
        return

    deleted_item_info = None
    async with data_lock:
        current_data_store = load_data(guild_id)
        items = current_data_store.get("items", [])
        if 0 <= item_index_to_delete < len(items):
            item_obj = items.pop(item_index_to_delete)
            deleted_item_info = f"Объект '{item_obj['object_name']}' в локации '{item_obj['location']}'"
            save_data(guild_id, items, current_data_store.get("allowed_roles", []))
            logging.info(
                f"Объект '{item_obj['object_name']}' в локации '{item_obj['location']}' "
                f"удалён пользователем {interaction.user} (ID: {interaction.user.id})."
            )
        else:
            await interaction.response.send_message("Объект не найден (возможно, уже удален).", ephemeral=True)
            return

    if deleted_item_info:
        await interaction.response.send_message(f"{deleted_item_info} успешно удален.", ephemeral=True)
        if interaction.channel:
            await show_data_module.update_show_data_message_for_channel(interaction.client, guild_id, interaction.channel.id)

@delete_data.autocomplete("item_to_delete")
async def delete_data_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    items = load_data(interaction.guild_id).get("items", [])
    choices = []
    for index, item in enumerate(items):
        name = f"{item['object_name']} @ {item['location']} (исчезнет <t:{item['time']}:R>)"
        value = f"item_{index}"
        if current.lower() in name.lower():
            choices.append(app_commands.Choice(name=name, value=value))
    return choices[:25]