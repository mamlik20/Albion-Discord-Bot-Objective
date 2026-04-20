# commands/show_data.py
import logging
import discord
from discord import app_commands
import json
import aiohttp
from datetime import datetime, timezone
from utils.data_store import show_data_messages, load_data, save_show_data_messages

EMOJI_PIN = "📍"
EMOJI_HOURGLASS = "⏳"


def get_object_icon(object_name: str, default_icon: str = EMOJI_PIN) -> str:
    try:
        with open("icons.json", "r", encoding="utf-8") as f:
            icon_rules = json.load(f)
        name_lower = object_name.lower()
        for keyword, icon in icon_rules.items():
            if keyword in name_lower:
                return icon
    except (FileNotFoundError, json.JSONDecodeError):
        return default_icon
    return default_icon


def get_abbreviated_name(full_name: str) -> str:
    try:
        with open("abbreviations.json", "r", encoding="utf-8") as f:
            rules = json.load(f)
        for long_name, short_name in rules.items():
            if full_name.startswith(long_name):
                return full_name.replace(long_name, short_name, 1)
    except (FileNotFoundError, json.JSONDecodeError):
        return full_name
    return full_name


def create_data_embed(guild_id: int) -> discord.Embed:
    items = sorted(load_data(guild_id).get("items", []), key=lambda x: x.get('time', 0))
    embed = discord.Embed(color=discord.Color.blue())

    if not items:
        embed.title = "Нет активных объектов"
        embed.description = "Список пуст. Добавьте новый объект с помощью команд `/add_data` , `/add_from_image` ."
    else:
        embed.title = "Активные объекты"
        for index, item in enumerate(items, 1):
            full_object_name = item.get('object_name', 'Неизвестный объект')
            abbreviated_name = get_abbreviated_name(full_object_name)
            icon = get_object_icon(abbreviated_name)
            location = item.get('location', 'Неизвестная локация')
            time_unix = item.get('time', 0)
            field_title = f"{icon} **{index}) {abbreviated_name} – {location}**"
            if time_unix:
                dt_object = datetime.fromtimestamp(time_unix, tz=timezone.utc)
                time_display_str = f"<t:{time_unix}:t>"
                relative_time_str = f"<t:{time_unix}:R>"
                utc_time_str = dt_object.strftime("%H:%M UTC")
                field_value = f"{EMOJI_HOURGLASS} {time_display_str} • {relative_time_str} • {utc_time_str}"
            else:
                field_value = f"{EMOJI_HOURGLASS} Время не указано"
            embed.add_field(name=field_title, value=field_value, inline=False)

    return embed


@app_commands.command(name="show_data", description="Показывает список всех добавленных объектов.")
async def show_data(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    channel_id = interaction.channel_id

    if not guild_id or not channel_id:
        await interaction.response.send_message("Эта команда должна использоваться на сервере в текстовом канале.",
                                                ephemeral=True)
        return

    await interaction.response.defer(thinking=True)

    if channel_id in show_data_messages:
        old_message_id = show_data_messages.pop(channel_id)
        save_show_data_messages(show_data_messages)
        try:
            old_message = await interaction.channel.fetch_message(old_message_id)
            await old_message.delete()
            logging.info(f"Удалено старое сообщение show_data (ID: {old_message_id}) в канале {channel_id}.")
        except (discord.NotFound, discord.Forbidden):
            logging.info(f"Не удалось найти или удалить старое сообщение show_data (ID: {old_message_id}).")
        except (discord.DiscordServerError, aiohttp.ClientError) as e:
            logging.warning(f"Временная ошибка при удалении сообщения show_data (ID: {old_message_id}): {e}")

    try:
        embed = create_data_embed(guild_id)
        sent_message = await interaction.followup.send(embed=embed)
        show_data_messages[channel_id] = sent_message.id
        save_show_data_messages(show_data_messages)
        logging.info(f"Создано новое отслеживаемое сообщение show_data (ID: {sent_message.id}) в канале {channel_id}.")
    except Exception as e:
        logging.error(f"Не удалось отправить новое сообщение show_data: {e}")
        await interaction.followup.send("Произошла ошибка при отображении данных.", ephemeral=True)


async def update_show_data_message_for_channel(bot: discord.Client, guild_id: int, channel_id: int):
    if channel_id not in show_data_messages:
        return

    message_id = show_data_messages[channel_id]
    try:
        channel = bot.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            if channel_id in show_data_messages:
                del show_data_messages[channel_id]
                save_show_data_messages(show_data_messages)
            return

        message_to_update = await channel.fetch_message(message_id)
        new_embed = create_data_embed(guild_id)
        await message_to_update.edit(embed=new_embed)
        logging.info(f"Сообщение show_data {message_id} в канале {channel_id} обновлено.")
    except discord.NotFound:
        if channel_id in show_data_messages:
            del show_data_messages[channel_id]
            save_show_data_messages(show_data_messages)
        logging.info(f"Сообщение show_data {message_id} не найдено, удалено из отслеживания.")
    except discord.Forbidden:
        logging.warning(f"Нет прав на редактирование сообщения show_data {message_id}.")
    except Exception as e:
        logging.error(f"Ошибка при обновлении сообщения show_data {message_id}: {e}")