import os
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from storage import JSONStore

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
JSON_PATH = os.getenv("JSON_PATH", "data/bot_data.json")
IMAGES_PATH = os.getenv("IMAGES_PATH", "resources/images")
TIMEZONE = os.getenv("TIMEZONE", "Europe/Paris")
DAILY_HOUR = int(os.getenv("DAILY_HOUR", "9"))
DAILY_MINUTE = int(os.getenv("DAILY_MINUTE", "0"))

intents = discord.Intents.default()
intents.members = True


class QuiEstCeBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.db = JSONStore(JSON_PATH)
        self.images_path = IMAGES_PATH
        self.timezone = TIMEZONE
        self.daily_hour = DAILY_HOUR
        self.daily_minute = DAILY_MINUTE

    async def setup_hook(self):
        await self.db.connect()
        await self.load_extension("src.admin")
        await self.load_extension("src.game")
        await self.load_extension("src.leaderboard")
        await self.tree.sync()

    async def close(self):
        await self.db.close()
        await super().close()


bot = QuiEstCeBot()


@bot.event
async def on_ready():
    print(f"Connecté en tant que {bot.user} ({bot.user.id})")


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "❌ You are not authorised to use this command.", ephemeral=True
        )
    else:
        raise error


bot.run(TOKEN)