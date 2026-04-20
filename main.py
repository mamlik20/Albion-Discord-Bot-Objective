import asyncio
import discord
from discord.ext import commands, tasks
import os
import logging
import json
from dotenv import load_dotenv

from commands import add_data, show_data, delete_data, set_allowed_roles, party_maker
from commands.add_from_image import add_from_image
from tasks import cleanup_data
from utils.data_store import save_guild_roles_map 

log_handler = logging.FileHandler('bot.log', encoding='utf-8')
log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(log_handler)
root_logger.addHandler(stream_handler)

logging.info("Логирование инициализировано.")

load_dotenv()
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
PROXY_URL = os.getenv("PROXY_URL")

if not DISCORD_BOT_TOKEN:
    raise ValueError("Критическая ошибка: Токен бота Discord не найден.")

def save_server_names(bot_instance):
    server_info = {str(guild.id): guild.name for guild in bot_instance.guilds}
    try:
        with open("server_names.json", "w", encoding="utf-8") as f:
            json.dump(server_info, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Не удалось сохранить server_names.json: {e}")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True

bot = commands.Bot(
    command_prefix='/', 
    intents=intents, 
    help_command=None, 
    proxy=PROXY_URL
)

bot.tree.add_command(add_data.add_data)
bot.tree.add_command(show_data.show_data)
bot.tree.add_command(delete_data.delete_data)
bot.tree.add_command(set_allowed_roles.set_allowed_roles)
bot.tree.add_command(add_from_image)

bot.tree.add_command(party_maker.setup_create)
bot.tree.add_command(party_maker.setup_delete)
bot.tree.add_command(party_maker.setup_list)
bot.tree.add_command(party_maker.game)

@tasks.loop(minutes=1)
async def cleanup_data_loop():
    await cleanup_data.cleanup_data(bot)

@bot.event
async def on_ready():
    logging.info(f'Bot {bot.user} is ready!')
    print(f'Bot {bot.user} is ready!')
    
    save_server_names(bot)
    
    for guild in bot.guilds:
        save_guild_roles_map(guild)

    if not cleanup_data_loop.is_running():
        cleanup_data_loop.start()

    try:
        synced = await bot.tree.sync()
        logging.info(f"Синхронизировано {len(synced)} команд")
    except Exception as e:
        logging.error(f"Ошибка синхронизации: {e}")

@bot.event
async def on_guild_join(guild):
    logging.info(f"Бот добавлен на сервер: {guild.name}")
    save_server_names(bot)
    save_guild_roles_map(guild)

@bot.event
async def on_guild_remove(guild):
    logging.info(f"Бот удален с сервера: {guild.name}")
    save_server_names(bot)

@bot.event
async def on_raw_reaction_add(payload):
    await party_maker.handle_reaction_add(bot, payload)

@bot.event
async def on_raw_reaction_remove(payload):
    await party_maker.handle_reaction_remove(bot, payload)

async def main():
    try:
        await bot.start(DISCORD_BOT_TOKEN)
    except Exception as e:
        logging.critical(f"Ошибка запуска: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())