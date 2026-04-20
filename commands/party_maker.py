# commands/party_maker.py

import discord
from discord import app_commands
import sqlite3
import re
import asyncio
import os
import logging
import json
from utils.data_store import load_allowed_roles, load_data

DATA_DIR = "bot_data"
DB_PATH = os.path.join(DATA_DIR, "game_bot.db")

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS setups (
    name TEXT PRIMARY KEY,
    party_count INTEGER,
    guild_id INTEGER
)
''')
cursor.execute('''
CREATE TABLE IF NOT EXISTS setup_parties (
    setup_name TEXT,
    party_number INTEGER,
    roles_text TEXT,
    FOREIGN KEY(setup_name) REFERENCES setups(name)
)
''')
cursor.execute('''
CREATE TABLE IF NOT EXISTS active_games (
    thread_id INTEGER PRIMARY KEY,
    message_id INTEGER,
    setup_name TEXT,
    channel_id INTEGER,
    guild_id INTEGER
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS user_stats (
    user_id INTEGER,
    guild_id INTEGER,
    username TEXT,
    added_count INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, guild_id)
)
''')
conn.commit()


def increment_user_stats(user_id, guild_id, username):
    try:
        local_conn = sqlite3.connect(DB_PATH)
        local_cur = local_conn.cursor()
        local_cur.execute('''
            INSERT INTO user_stats (user_id, guild_id, username, added_count)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(user_id, guild_id) 
            DO UPDATE SET added_count = added_count + 1, username = ?
        ''', (user_id, guild_id, username, username))
        local_conn.commit()
        local_conn.close()
    except Exception as e:
        logging.error(f"Ошибка обновления статистики: {e}")


def check_permissions(interaction: discord.Interaction) -> bool:
    """Проверка прав для слэш-команд"""
    guild_id = interaction.guild_id
    if not guild_id: return False
    if interaction.user.id == interaction.guild.owner_id: return True

    allowed_role_ids = load_allowed_roles(guild_id)
    if not allowed_role_ids:
        return interaction.user.guild_permissions.administrator
        
    user_role_ids = [role.id for role in interaction.user.roles]
    return any(role_id in allowed_role_ids for role_id in user_role_ids)

def check_permissions_user(user: discord.Member) -> bool:
    """Проверка прав для РЕАКЦИЙ"""
    if user.id == user.guild.owner_id: return True
    
    data = load_data(user.guild.id)
    party_roles = data.get("party_admin_roles", [])
    
    if not party_roles:
        party_roles = data.get("allowed_roles", [])
    
    if not party_roles:
        return user.guild_permissions.administrator
        
    user_role_ids = [r.id for r in user.roles]
    return any(rid in party_roles for rid in user_role_ids)

def parse_slot_info(content: str):
    """
    Пытается понять, что написал пользователь.
    Возвращает (party_num, slot_num) или (None, None).
    """
    match_complex = re.search(r'(\d+)[\s\-\\\/]+(\d+)', content)
    if match_complex:
        return int(match_complex.group(1)), int(match_complex.group(2))
    
    digits_only = re.sub(r'\D', '', content)
    if digits_only.isdigit():
        return 1, int(digits_only)
        
    return None, None


async def update_roster(bot, message_id, channel_id, user_to_add, party_num, slot_num, action="add"):
    try:
        channel = bot.get_channel(channel_id)
        if not channel: return
        msg = await channel.fetch_message(message_id)
    except Exception as e:
        logging.error(f"PartyMaker: Ошибка получения сообщения {message_id}: {e}")
        return

    if not msg.embeds: return

    embed = msg.embeds[0]
    field_index = party_num - 1
    
    if field_index >= len(embed.fields): return

    field_value = embed.fields[field_index].value
    lines = field_value.split('\n')
    new_lines = []
    updated = False

    regex = re.compile(r'^(\d+)\.\s*(.*?)(?:\s*<@\d+>)?$')

    for line in lines:
        match = regex.match(line.strip())
        if match:
            curr_slot = int(match.group(1))
            role_name = match.group(2)
            
            if curr_slot == slot_num:
                if action == "add" and user_to_add:
                    new_lines.append(f"{curr_slot}. {role_name} {user_to_add.mention}")
                else:
                    new_lines.append(f"{curr_slot}. {role_name}")
                updated = True
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    if updated:
        new_text = "\n".join(new_lines)
        
        if len(new_text) > 1024:
            logging.warning(f"PartyMaker: Лимит символов в пачке {party_num}. Сокращаем.")
            optimized_lines = []
            for line in new_lines:
                match = re.match(r'^(\d+\.)\s*(.*?)(?:\s*(<@\d+>))?$', line)
                if match:
                    prefix = match.group(1)
                    r_text = match.group(2)
                    mention = match.group(3) if match.group(3) else ""
                    
                    if len(r_text) > 15:
                        r_text = r_text[:13] + ".."
                    
                    optimized_lines.append(f"{prefix} {r_text} {mention}".strip())
                else:
                    optimized_lines.append(line)
            
            new_text = "\n".join(optimized_lines)
            
            if len(new_text) > 1024:
                try:
                    if channel and isinstance(channel, discord.TextChannel):
                        # Пытаемся сообщить в ветку о переполнении
                        thread_id_row = cursor.execute('SELECT thread_id FROM active_games WHERE message_id = ?', (message_id,)).fetchone()
                        if thread_id_row:
                            thread = bot.get_channel(thread_id_row[0])
                            if thread:
                                await thread.send(f"⚠️ Пачка №{party_num} переполнена. Не могу добавить игрока.")
                except: pass
                return

        embed.set_field_at(field_index, name=embed.fields[field_index].name, value=new_text, inline=True)
        await msg.edit(embed=embed)


@app_commands.command(name="setup_create", description="[Party] Создать новый шаблон пачек")
@app_commands.default_permissions(administrator=True)
async def setup_create(interaction: discord.Interaction, name: str, party_count: int):
    if not check_permissions(interaction):
        await interaction.response.send_message("❌ У вас нет прав.", ephemeral=True)
        return

    cursor.execute('SELECT name FROM setups WHERE name = ?', (name,))
    if cursor.fetchone():
        await interaction.response.send_message(f"❌ Шаблон **{name}** уже существует.", ephemeral=True)
        return

    await interaction.response.send_message(f"Создание шаблона **{name}** ({party_count} пачек).\nОтправляйте списки ролей сообщениями.", ephemeral=True)

    parties_data = []
    def check(m):
        return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id

    for i in range(1, party_count + 1):
        await interaction.followup.send(f"📋 **Пачка №{i}** - жду список ролей:", ephemeral=True)
        try:
            msg = await interaction.client.wait_for('message', check=check, timeout=300.0)
        except asyncio.TimeoutError:
            await interaction.followup.send("⏳ Время вышло.", ephemeral=True)
            return

        raw_lines = msg.content.strip().split('\n')
        processed_lines = []
        for idx, line in enumerate(raw_lines, 1):
            clean_line = line.strip()
            if not re.match(r'^\d+[\.\)]', clean_line):
                processed_lines.append(f"{idx}. {clean_line}")
            else:
                processed_lines.append(clean_line)
        
        final_text = "\n".join(processed_lines)
        parties_data.append((i, final_text))
        try: await msg.delete()
        except: pass

    cursor.execute('INSERT INTO setups (name, party_count, guild_id) VALUES (?, ?, ?)', (name, party_count, interaction.guild_id))
    for p_num, p_text in parties_data:
        cursor.execute('INSERT INTO setup_parties (setup_name, party_number, roles_text) VALUES (?, ?, ?)', (name, p_num, p_text))
    conn.commit()

    await interaction.followup.send(f"✅ Шаблон **{name}** сохранен!", ephemeral=True)


@app_commands.command(name="setup_delete", description="[Party] Удалить шаблон")
@app_commands.default_permissions(administrator=True)
async def setup_delete(interaction: discord.Interaction, name: str):
    if not check_permissions(interaction):
        await interaction.response.send_message("❌ Нет прав.", ephemeral=True)
        return

    cursor.execute('DELETE FROM setups WHERE name = ?', (name,))
    cursor.execute('DELETE FROM setup_parties WHERE setup_name = ?', (name,))
    conn.commit()
    await interaction.response.send_message(f"🗑️ Шаблон **{name}** удален.", ephemeral=True)


@app_commands.command(name="setup_list", description="[Party] Список шаблонов")
@app_commands.default_permissions(administrator=True)
async def setup_list(interaction: discord.Interaction):
    cursor.execute('SELECT name, party_count FROM setups') 
    rows = cursor.fetchall()
    if not rows:
        await interaction.response.send_message("Нет сохраненных шаблонов.", ephemeral=True)
        return
    text = "**Доступные шаблоны:**\n" + "\n".join([f"- **{r[0]}** ({r[1]} пачек)" for r in rows])
    await interaction.response.send_message(text, ephemeral=True)


@app_commands.command(name="game", description="[Party] Начать сбор")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(setup_name="Название шаблона", start_time="Время начала (например: 20:00 МСК)")
async def game(interaction: discord.Interaction, setup_name: str, start_time: str):
    cursor.execute('SELECT party_count FROM setups WHERE name = ?', (setup_name,))
    res = cursor.fetchone()
    if not res:
        await interaction.response.send_message(f"❌ Шаблон **{setup_name}** не найден.", ephemeral=True)
        return
    
    cursor.execute('SELECT party_number, roles_text FROM setup_parties WHERE setup_name = ? ORDER BY party_number ASC', (setup_name,))
    parties = cursor.fetchall()

    embed = discord.Embed(title=f"📢 Сбор", color=discord.Color.gold())
    embed.description = (
        f"⏰ **Время начала:** {start_time}\n\n"
        "Чтобы записаться, напишите в ветку ниже `НомерПачки-Слот` (например: `2-5`) или просто номер слота (например `14`)."
    )
    
    for p_num, p_text in parties:
        embed.add_field(name=f"🛡️ Пачка {p_num}", value=p_text, inline=True)

    await interaction.response.send_message("Создаю списки...", ephemeral=True)
    msg = await interaction.channel.send(content="@everyone", embed=embed)
    
    thread = await msg.create_thread(name=f"Регистрация {setup_name}", auto_archive_duration=1440)
    await thread.send("📝 **Пишите сюда номер пачки и роль.**\nПример: `1-10` или просто `10` (для 1 пачки).\nКолер подтвердит запись галочкой ✅.")

    cursor.execute('INSERT INTO active_games (thread_id, message_id, setup_name, channel_id, guild_id) VALUES (?, ?, ?, ?, ?)', 
                   (thread.id, msg.id, setup_name, interaction.channel.id, interaction.guild_id))
    conn.commit()


# --- ОБРАБОТЧИКИ СОБЫТИЙ ---

async def handle_reaction_add(bot, payload):
    if str(payload.emoji) != "✅": return
    if payload.user_id == bot.user.id: return

    channel = bot.get_channel(payload.channel_id)
    if not isinstance(channel, discord.Thread): return

    cursor.execute('SELECT message_id, channel_id FROM active_games WHERE thread_id = ?', (payload.channel_id,))
    row = cursor.fetchone()
    if not row: return

    guild = bot.get_guild(payload.guild_id)
    if not guild: return
    user = guild.get_member(payload.user_id)
    
    if not user or not check_permissions_user(user): return

    try: reacted_msg = await channel.fetch_message(payload.message_id)
    except: return

    party_num, slot_num = parse_slot_info(reacted_msg.content)
    
    if party_num is not None and slot_num is not None:
        await update_roster(bot, row[0], row[1], reacted_msg.author, party_num, slot_num, action="add")


async def handle_reaction_remove(bot, payload):
    if str(payload.emoji) != "✅": return
    
    channel = bot.get_channel(payload.channel_id)
    if not isinstance(channel, discord.Thread): return

    cursor.execute('SELECT message_id, channel_id FROM active_games WHERE thread_id = ?', (payload.channel_id,))
    row = cursor.fetchone()
    if not row: return
    
    guild = bot.get_guild(payload.guild_id)
    if not guild: return
    user = guild.get_member(payload.user_id)
    
    if not user or not check_permissions_user(user):
        return

    try: reacted_msg = await channel.fetch_message(payload.message_id)
    except: return

    party_num, slot_num = parse_slot_info(reacted_msg.content)

    if party_num is not None and slot_num is not None:
        await update_roster(bot, row[0], row[1], None, party_num, slot_num, action="remove")