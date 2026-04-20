# commands/set_allowed_roles.py
import discord
from discord import app_commands
from utils.data_store import save_allowed_roles
from typing import List


@app_commands.command(name="set_allowed_roles", description="Управляет ролями для команд добавления/удаления.")
@app_commands.describe(roles="Выберите роли. Если не выбрано, список будет очищен.")
@app_commands.default_permissions(administrator=True)
async def set_allowed_roles(interaction: discord.Interaction, roles: str = None):
    guild_id = interaction.guild_id
    if not guild_id: return

    if not roles:
        save_allowed_roles(guild_id, [])
        await interaction.response.send_message("Список разрешенных ролей очищен.", ephemeral=True)
        return

    role_ids = [int(r_id) for r_id in roles.split(',') if r_id.isdigit()]
    selected_roles = [interaction.guild.get_role(r_id) for r_id in role_ids]
    valid_roles = [r for r in selected_roles if r]

    save_allowed_roles(guild_id, [r.id for r in valid_roles])
    await interaction.response.send_message(
        f"Установлены разрешенные роли: {', '.join([r.name for r in valid_roles]) if valid_roles else 'Список пуст'}.",
        ephemeral=True
    )


@set_allowed_roles.autocomplete("roles")
async def roles_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    guild = interaction.guild
    choices = []
    current_selected_ids = [p.strip() for p in current.split(',') if p.strip()]

    for role in guild.roles:
        if role.is_bot_managed() or role.is_integration() or role == guild.default_role:
            continue

        role_id_str = str(role.id)
        if role_id_str in current_selected_ids:
            continue

        if current.split(',')[-1].strip().lower() in role.name.lower():
            new_value = ",".join(current_selected_ids + [role_id_str])
            choices.append(app_commands.Choice(name=role.name, value=new_value))

    return choices[:25]