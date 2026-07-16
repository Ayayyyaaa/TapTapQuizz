import discord
from discord import app_commands
from discord.ext import commands


class AdminCog(commands.GroupCog, name="config", description="Configuration du jeu Qui-est-ce"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="channel", description="Définit le salon des annonces quotidiennes")
    @app_commands.describe(channel="Salon textuel cible")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self.bot.db.set_channel(interaction.guild_id, channel.id)
        await interaction.response.send_message(
            f"✅ Le salon d'annonce est désormais {channel.mention}.", ephemeral=True
        )

    @app_commands.command(name="role", description="Définit le rôle mentionné lors de l'annonce quotidienne")
    @app_commands.describe(role="Rôle à mentionner")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config_role(self, interaction: discord.Interaction, role: discord.Role):
        await self.bot.db.set_role(interaction.guild_id, role.id)
        await interaction.response.send_message(
            f"✅ Le rôle {role.mention} sera mentionné chaque jour.", ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(AdminCog(bot))
