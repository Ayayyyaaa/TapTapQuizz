import os
import time
import unicodedata
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks

from game_logic import pick_daily_character


def normalize(text: str) -> str:
    text = text.strip().lower()
    text = unicodedata.normalize("NFD", text)
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def today_str(tz_name: str) -> str:
    return datetime.now(ZoneInfo(tz_name)).strftime("%Y-%m-%d")


class GuessModal(discord.ui.Modal, title="Qui est-ce ?"):
    guess_input = discord.ui.TextInput(label="Nom du personnage", placeholder="Ex : Mario", max_length=50)

    def __init__(self, cog: "GameCog", guild_id: int, date_str: str, character_name: str):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        self.date_str = date_str
        self.character_name = character_name

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.handle_guess(
            interaction, self.guild_id, self.date_str, self.character_name, str(self.guess_input.value)
        )


class GuessView(discord.ui.View):
    def __init__(self, cog: "GameCog", guild_id: int, date_str: str, character_name: str, timeout: float):
        super().__init__(timeout=max(timeout, 1))
        self.cog = cog
        self.guild_id = guild_id
        self.date_str = date_str
        self.character_name = character_name

    @discord.ui.button(label="Proposer une réponse", style=discord.ButtonStyle.primary, emoji="🕵️")
    async def guess_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            GuessModal(self.cog, self.guild_id, self.date_str, self.character_name)
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

    @app_commands.command(name="guess", description="Tente de deviner le personnage du jour !")
    async def guess(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        date_str = today_str(self.bot.timezone)
        daily = await self.bot.db.get_daily(guild_id, date_str)

        if daily is None:
            await interaction.response.send_message(
                "Aucun défi n'est encore disponible aujourd'hui. Vérifie `/config channel`.",
                ephemeral=True,
            )
            return

        character_name = daily["character_name"]
        image_file = daily["image_file"]

        attempt = await self.bot.db.get_attempt(guild_id, interaction.user.id, date_str)

        if attempt and attempt["finished"]:
            result = "réussi 🎉" if attempt["finished"] == 1 else "échoué 😢"
            await interaction.response.send_message(
                f"Tu as déjà tenté ta chance aujourd'hui ({result}). Réponse : **{character_name}**. À demain !",
                ephemeral=True,
            )
            return

        if attempt is None:
            await self.bot.db.create_attempt(guild_id, interaction.user.id, date_str)
            remaining = 30
        else:
            elapsed = time.time() - attempt["start_time"]
            if elapsed > 30:
                await self.bot.db.finish_attempt(guild_id, interaction.user.id, date_str, False, 0)
                await interaction.response.send_message(
                    f"⏰ Trop tard ! La réponse était **{character_name}**.", ephemeral=True
                )
                return
            remaining = max(1, int(30 - elapsed))

        path = os.path.join(self.bot.images_path, image_file)
        if not os.path.isfile(path):
            await interaction.response.send_message("Erreur interne : image introuvable.", ephemeral=True)
            return

        file = discord.File(path, filename=image_file)
        embed = discord.Embed(
            title="🕵️ Qui est-ce ?",
            description=f"Tu as **{remaining} secondes** et jusqu'à **2 essais** pour deviner !",
            color=discord.Color.blurple(),
        )
        embed.set_image(url=f"attachment://{image_file}")

        view = GuessView(self, guild_id, date_str, character_name, timeout=remaining)
        await interaction.response.send_message(embed=embed, file=file, view=view, ephemeral=True)

    async def handle_guess(self, interaction, guild_id, date_str, character_name, guess_text):
        user_id = interaction.user.id
        attempt = await self.bot.db.get_attempt(guild_id, user_id, date_str)

        if attempt is None or attempt["finished"]:
            await interaction.response.send_message(
                "Cette session de jeu n'est plus valide, relance `/guess`.", ephemeral=True
            )
            return

        elapsed = time.time() - attempt["start_time"]
        if elapsed > 30:
            await self.bot.db.finish_attempt(guild_id, user_id, date_str, False, 0)
            await interaction.response.send_message(
                f"⏰ Trop tard ! La réponse était **{character_name}**.", ephemeral=True
            )
            return

        attempt_count = attempt["attempt_count"] + 1

        if normalize(guess_text) == normalize(character_name):
            points = 3 if attempt_count == 1 else 1
            await self.bot.db.finish_attempt(guild_id, user_id, date_str, True, points)
            await self.bot.db.add_points(guild_id, user_id, points)
            await interaction.response.send_message(
                f"✅ Bravo, c'était **{character_name}** ! Tu gagnes **{points} point(s)**.", ephemeral=True
            )
            return

        if attempt_count >= 2:
            await self.bot.db.finish_attempt(guild_id, user_id, date_str, False, 0)
            await interaction.response.send_message(
                f"❌ Perdu ! La réponse était **{character_name}**.", ephemeral=True
            )
            return

        await self.bot.db.update_attempt_count(guild_id, user_id, date_str, attempt_count)
        remaining = max(1, int(30 - elapsed))
        view = GuessView(self, guild_id, date_str, character_name, timeout=remaining)
        await interaction.response.send_message(
            f"❌ Mauvaise réponse. Il te reste **1 essai** ({remaining}s restantes) !",
            view=view,
            ephemeral=True,
        )

    @tasks.loop(minutes=1)
    async def daily_task(self):
        tz = ZoneInfo(self.bot.timezone)
        now = datetime.now(tz)
        if (now.hour, now.minute) != (self.bot.daily_hour, self.bot.daily_minute):
            return

        today = now.strftime("%Y-%m-%d")
        yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")

        for guild in self.bot.guilds:
            config = await self.bot.db.get_guild_config(guild.id)
            if not config or not config.get("channel_id"):
                continue
            if await self.bot.db.get_daily(guild.id, today):
                continue

            history = await self.bot.db.get_character_history(guild.id)
            character_name, image_file = pick_daily_character(self.bot.images_path, history)
            if character_name is None:
                continue

            await self.bot.db.set_daily(guild.id, today, character_name, image_file)
            await self.bot.db.update_character_history(guild.id, character_name, today)

            channel = guild.get_channel(config["channel_id"])
            if channel is None:
                continue

            role_mention = f"<@&{config['role_id']}>" if config.get("role_id") else None

            previous = await self.bot.db.get_daily(guild.id, yesterday)
            previous_text = (
                f"Le personnage d'hier était **{previous['character_name']}** !"
                if previous else "Pas de défi hier."
            )

            top = await self.bot.db.get_leaderboard(guild.id, 5)
            if top:
                lines = []
                for i, row in enumerate(top, start=1):
                    member = guild.get_member(row["user_id"])
                    name = member.display_name if member else f"Utilisateur {row['user_id']}"
                    lines.append(f"**{i}.** {name} — {row['points']} pts")
                leaderboard_text = "\n".join(lines)
            else:
                leaderboard_text = "Aucun score enregistré pour l'instant."

            embed = discord.Embed(
                title="🎮 Nouveau défi Qui-est-ce !",
                description=f"{previous_text}\n\nUn nouveau personnage vous attend, tentez `/guess` !",
                color=discord.Color.gold(),
            )
            embed.add_field(name="🏆 Top 5", value=leaderboard_text, inline=False)

            await channel.send(content=role_mention, embed=embed)

    @daily_task.before_loop
    async def before_daily_task(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(GameCog(bot))
