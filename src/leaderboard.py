import discord
from discord import app_commands
from discord.ext import commands


class LeaderboardCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="leaderboard", description="Displays the points table")
    async def leaderboard(self, interaction: discord.Interaction):
        rows = await self.bot.db.get_leaderboard(interaction.guild_id, 10)
        if not rows:
            await interaction.response.send_message("No score so far.", ephemeral=True)
            return

        lines = []
        for i, row in enumerate(rows, start=1):
            member = interaction.guild.get_member(row["user_id"])
            name = member.display_name if member else f"User {row['user_id']}"
            lines.append(f"**{i}.** {name} — {row['points']} pts")

        embed = discord.Embed(title="<:top1:1527327610613530736> Who's that ranking", description="\n".join(lines), color=discord.Color.blue())
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(LeaderboardCog(bot))
