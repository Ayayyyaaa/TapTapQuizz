import discord
from discord import app_commands
from discord.ext import commands


class AdminCog(commands.GroupCog, name="config", description="Setting up the game Taple"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="channel", description="Defines the daily announcements channel")
    @app_commands.describe(channel="Target channel")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self.bot.db.set_channel(interaction.guild_id, channel.id)
        await interaction.response.send_message(
            f"<a:poussin:1527327276524503041> The announcement channel is now {channel.mention}.", ephemeral=True
        )

    @app_commands.command(name="role", description="Defines the role ping in the daily announcement")
    @app_commands.describe(role="Role to be ping")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config_role(self, interaction: discord.Interaction, role: discord.Role):
        await self.bot.db.set_role(interaction.guild_id, role.id)
        await interaction.response.send_message(
            f"<a:poussin:1527327276524503041> The role {role.mention} will be mentioned every day.", ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(AdminCog(bot))
