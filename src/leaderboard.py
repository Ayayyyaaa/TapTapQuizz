from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands


def today_str(tz_name: str) -> str:
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo(tz_name)).strftime("%Y-%m-%d")


class LeaderboardCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _resolve_display_name(self, user_id: int) -> str:
        user = self.bot.get_user(user_id)
        if user is None:
            try:
                user = await self.bot.fetch_user(user_id)
            except discord.HTTPException:
                user = None
        return user.display_name if user else f"User {user_id}"

    @app_commands.command(name="leaderboard", description="Displays the points table")
    async def leaderboard(self, interaction: discord.Interaction):
        rows = await self.bot.db.get_leaderboard(10)
        if not rows:
            await interaction.response.send_message("No score so far.", ephemeral=True)
            return

        lines = []
        for i, row in enumerate(rows, start=1):
            name = await self._resolve_display_name(row["user_id"])
            lines.append(f"**{i}.** {name} — {row['points']} pts")

        embed = discord.Embed(
            title="<:top1:1527327610613530736> Who's that ranking (all servers)",
            description="\n".join(lines),
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="participation", description="Shows who played and the result for a given day")
    @app_commands.describe(day="Date in YYYY-MM-DD format (default: today)")
    async def participation(self, interaction: discord.Interaction, day: str = None):
        date_str = day or today_str(self.bot.timezone)

        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            await interaction.response.send_message(
                "Invalid date format; please use YYYY-MM-DD (e.g. 2026-07-17).", ephemeral=True
            )
            return

        attempts = await self.bot.db.get_attempts_for_date(date_str)
        if not attempts:
            await interaction.response.send_message(
                f"No one has played the **{date_str}**.", ephemeral=True
            )
            return

        found, failed, pending = [], [], []
        for uid_str, entry in attempts.items():
            name = await self._resolve_display_name(int(uid_str))
            if entry["finished"] == 1:
                found.append(f"**{name}** ({entry['points_earned']} pt(s))")
            elif entry["finished"] == 2:
                failed.append(f"**{name}**")
            else:
                pending.append(f"**{name}**")

        embed = discord.Embed(
            title=f"<:announce:1527327218500636692> Attendance on {date_str}",
            color=discord.Color.green(),
        )
        embed.add_field(
            name=f"<:crown:1527327497962651860> Found ({len(found)})",
            value="\n".join(found) if found else "—",
            inline=False,
        )
        embed.add_field(
            name=f"<:secu:1527327363677945866> Failed ({len(failed)})",
            value="\n".join(failed) if failed else "—",
            inline=False,
        )
        if pending:
            embed.add_field(
                name=f"<:notif:1527327608490950717> Not finished ({len(pending)})",
                value="\n".join(pending),
                inline=False,
            )

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(LeaderboardCog(bot))