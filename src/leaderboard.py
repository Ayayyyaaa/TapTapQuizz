import discord
from discord import app_commands
from discord.ext import commands


class LeaderboardCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="leaderboard", description="Affiche le classement des points")
    async def leaderboard(self, interaction: discord.Interaction):
        rows = await self.bot.db.get_leaderboard(interaction.guild_id, 10)
        if not rows:
            await interaction.response.send_message("Aucun score pour le moment.", ephemeral=True)
            return

        lines = []
        for i, row in enumerate(rows, start=1):
            member = interaction.guild.get_member(row["user_id"])
            name = member.display_name if member else f"Utilisateur {row['user_id']}"
            lines.append(f"**{i}.** {name} — {row['points']} pts")

        embed = discord.Embed(title="🏆 Classement Qui-est-ce", description="\n".join(lines), color=discord.Color.blue())
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(LeaderboardCog(bot))
