import os
import time
import unicodedata
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks

from game_logic import pick_daily_character
from .emojis import characters as character_emojis


def normalize(text: str) -> str:
    text = text.strip().lower()
    text = unicodedata.normalize("NFD", text)
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def today_str(tz_name: str) -> str:
    return datetime.now(ZoneInfo(tz_name)).strftime("%Y-%m-%d")


def format_character_with_emoji(name: str) -> str:
    """Retourne le nom du perso, précédé de son gif s'il existe dans emojis.py."""
    emoji = character_emojis.get(name.lower())
    if emoji:
        return f"**{name}** {emoji}"
    return f"**{name}**"


class GuessModal(discord.ui.Modal, title="Who-is ?"):
    guess_input = discord.ui.TextInput(label="Character name", placeholder="Ex : Scythe", max_length=50)

    def __init__(self, cog: "GameCog", date_str: str, character_name: str):
        super().__init__()
        self.cog = cog
        self.date_str = date_str
        self.character_name = character_name

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.handle_guess(
            interaction, self.date_str, self.character_name, str(self.guess_input.value)
        )


class GuessView(discord.ui.View):
    def __init__(self, cog: "GameCog", date_str: str, character_name: str, timeout: float):
        super().__init__(timeout=max(timeout, 1))
        self.cog = cog
        self.date_str = date_str
        self.character_name = character_name

    @discord.ui.button(label="Suggest an answer", style=discord.ButtonStyle.primary, emoji="🕵️")
    async def guess_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            GuessModal(self.cog, self.date_str, self.character_name)
        )

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


class GameCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.daily_task.start()

    def cog_unload(self):
        self.daily_task.cancel()

    @app_commands.command(name="guess", description="Have a go at guessing today’s character!")
    async def guess(self, interaction: discord.Interaction):
        date_str = today_str(self.bot.timezone)
        daily = await self.bot.db.get_daily(date_str)

        if daily is None:
            await interaction.response.send_message(
                "There are no challenges available today. Check `/config channel`.",
                ephemeral=True,
            )
            return

        character_name = daily["character_name"]
        image_file = daily["image_file"]

        attempt = await self.bot.db.get_attempt(interaction.user.id, date_str)

        if attempt and attempt["finished"]:
            await interaction.response.send_message(
                f"<:announce:1527327218500636692> You have already tried your luck today! See you tomorrow! <:calendar:1527327450823135303>",
                ephemeral=True,
            )
            return

        if attempt is None:
            await self.bot.db.create_attempt(interaction.user.id, date_str)
            remaining = 45
        else:
            elapsed = time.time() - attempt["start_time"]
            if elapsed > 45:
                await self.bot.db.finish_attempt(interaction.user.id, date_str, False, 0)
                await interaction.response.send_message(
                    f"<:notif:1527327608490950717> Too late! See you tomorrow! <:calendar:1527327450823135303>", ephemeral=True
                )
                return
            remaining = max(1, int(45 - elapsed))

        path = os.path.join(self.bot.images_path, image_file)
        if not os.path.isfile(path):
            await interaction.response.send_message("Error, no images", ephemeral=True)
            return

        file = discord.File(path, filename=image_file)
        embed = discord.Embed(
            title="<:random:1527327265166201012> Who is ?",
            description=f"You have **{remaining} seconds** and up to **2 attempts** to guess!",
            color=discord.Color.blurple(),
        )
        embed.set_image(url=f"attachment://{image_file}")

        view = GuessView(self, date_str, character_name, timeout=remaining)
        await interaction.response.send_message(embed=embed, file=file, view=view, ephemeral=True)

    async def handle_guess(self, interaction, date_str, character_name, guess_text):
        user_id = interaction.user.id
        attempt = await self.bot.db.get_attempt(user_id, date_str)

        if attempt is None or attempt["finished"]:
            await interaction.response.send_message(
                "Invalid, retype `/guess`.", ephemeral=True
            )
            return

        elapsed = time.time() - attempt["start_time"]
        if elapsed > 45:
            await self.bot.db.finish_attempt(user_id, date_str, False, 0)
            await interaction.response.send_message(
                f"<:notif:1527327608490950717> Too late! See you tomorrow! <:calendar:1527327450823135303>", ephemeral=True
            )
            return

        attempt_count = attempt["attempt_count"] + 1

        if normalize(guess_text) == normalize(character_name):
            points = 3 if attempt_count == 1 else 1
            await self.bot.db.finish_attempt(user_id, date_str, True, points)
            await self.bot.db.add_points(user_id, points)
            await interaction.response.send_message(
                f"<:crown:1527327497962651860> Well done {interaction.user.mention}, you found the daily character ! You win **{points} point(s)**.",
            )
            return

        if attempt_count >= 2:
            await self.bot.db.finish_attempt(user_id, date_str, False, 0)
            await interaction.response.send_message(
                f"<a:poussin:1527327276524503041> Wrong ! See you tomorrow! <:calendar:1527327450823135303>", ephemeral=True
            )
            return

        await self.bot.db.update_attempt_count(user_id, date_str, attempt_count)
        remaining = max(1, int(45 - elapsed))
        view = GuessView(self, date_str, character_name, timeout=remaining)
        await interaction.response.send_message(
            f"<a:poussin:1527327276524503041> Wrong answer. You have **1 attempt** ({remaining}s) left!",
            view=view,
            ephemeral=True,
        )

    async def _resolve_display_name(self, user_id: int) -> str:
        user = self.bot.get_user(user_id)
        if user is None:
            try:
                user = await self.bot.fetch_user(user_id)
            except discord.HTTPException:
                user = None
        return user.display_name if user else f"User {user_id}"

    @tasks.loop(minutes=1)
    async def daily_task(self):
        tz = ZoneInfo(self.bot.timezone)
        now = datetime.now(tz)
        if (now.hour, now.minute) != (self.bot.daily_hour, self.bot.daily_minute):
            return

        today = now.strftime("%Y-%m-%d")
        yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")

        # Le personnage du jour est global : on le tire une seule fois,
        # partagé par tous les serveurs.
        daily = await self.bot.db.get_daily(today)
        if daily is None:
            history = await self.bot.db.get_character_history()
            character_name, image_file = pick_daily_character(self.bot.images_path, history)
            if character_name is None:
                return  # aucune image disponible
            await self.bot.db.set_daily(today, character_name, image_file)
            await self.bot.db.update_character_history(character_name, today)
            daily = await self.bot.db.get_daily(today)

        previous = await self.bot.db.get_daily(yesterday)
        previous_text = (
            f"Yesterday's character was {format_character_with_emoji(previous['character_name'])} !"
            if previous else "No challenge yesterday."
        )

        top = await self.bot.db.get_leaderboard(5)
        if top:
            lines = []
            for i, row in enumerate(top, start=1):
                name = await self._resolve_display_name(row["user_id"])
                lines.append(f"**{i}.** {name} — {row['points']} pts")
            leaderboard_text = "\n".join(lines)
        else:
            leaderboard_text = "No scores have been recorded so far."

        embed = discord.Embed(
            title="<:announce:1527327218500636692> New 'Who's That?' challenge!",
            description=f"{previous_text}\n\nA new character is waiting for you, type `/guess` and try to win!",
            color=discord.Color.gold(),
        )
        embed.add_field(name="<:top1:1527327610613530736> Top 5 (all servers)", value=leaderboard_text, inline=False)

        configs = await self.bot.db.get_all_guild_configs()
        for gid_str, config in configs.items():
            if not config.get("channel_id"):
                continue
            if config.get("last_announced") == today:
                continue

            guild = self.bot.get_guild(int(gid_str))
            if guild is None:
                continue
            channel = guild.get_channel(config["channel_id"])
            if channel is None:
                continue

            role_mention = f"<@&{config['role_id']}>" if config.get("role_id") else None
            await channel.send(content=role_mention, embed=embed)
            await self.bot.db.set_last_announced(int(gid_str), today)

    @daily_task.before_loop
    async def before_daily_task(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(GameCog(bot))